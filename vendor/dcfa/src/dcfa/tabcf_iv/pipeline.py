"""Deterministic no-LLM TabCF Analyst v1 vertical slice."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dcfa.audit import AuditTrail
from dcfa.cache import ResultCache
from dcfa.canonical import (
    canonical_json_bytes,
    content_id,
    file_sha256,
    is_sha256_digest,
    sha256_digest,
)
from dcfa.constants import EstimatorBackend, SupportStatus, WarningSeverity
from dcfa.errors import DCFAError, ErrorCode
from dcfa.evidence import (
    EvidenceLedger,
    build_evidence_record,
    validate_bundle_evidence,
)
from dcfa.output import require_fresh_output_directory
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.reporting import render_bundle_plot, render_markdown_report
from dcfa.schemas import (
    AnalysisSpecification,
    DatasetManifest,
    EvidenceRecord,
    QueryResult,
    QuerySpecification,
    ResultBundle,
    RunManifest,
    SupportAssessment,
    WarningRecord,
)
from dcfa.tabcf_iv.backend import StatisticalBackend, make_backend
from dcfa.tabcf_iv.diagnostics import assess_support, compute_diagnostics
from dcfa.tabcf_iv.estimands import (
    canonicalize_cdf,
    exact_grid_index,
    interpolate_risks,
    invert_cdf,
)
from dcfa.tabcf_iv.validation import (
    validate_tabcf_data,
    validate_tabcf_dataset_manifest,
    validate_tabcf_specification,
)

BackendFactory = Callable[[AnalysisSpecification], StatisticalBackend]


@dataclass(frozen=True)
class AnalysisRun:
    bundle: ResultBundle
    ledger: EvidenceLedger
    audit: AuditTrail
    run_manifest: RunManifest
    artifact_paths: tuple[tuple[str, Path], ...]
    backend_fit_calls: int


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _write_json(path: Path, value: object) -> None:
    _atomic_write(path, canonical_json_bytes(value))


def _write_jsonl(path: Path, values: tuple[object, ...]) -> None:
    payload = b"\n".join(canonical_json_bytes(value) for value in values) + b"\n"
    _atomic_write(path, payload)


def _default_backend_factory(specification: AnalysisSpecification) -> StatisticalBackend:
    backend_parameters = dict(specification.backend_parameters)
    return make_backend(
        specification.estimator_backend,
        execution_profile=specification.execution_profile,
        seed=specification.seed,
        model_path=backend_parameters.get("model_path", "auto"),
        model_artifact_hash=backend_parameters.get("model_artifact_hash", ""),
        runtime_image_digest=backend_parameters.get("runtime_image_digest", ""),
    )


def _support_for_x(support: tuple[SupportAssessment, ...], x_value: float) -> SupportAssessment:
    for assessment in support:
        if abs(assessment.x - float(x_value)) <= 1e-10:
            return assessment
    raise DCFAError(
        ErrorCode.INVALID_SPECIFICATION,
        f"Query intervention x={x_value} is absent from intervention_grid.",
        stage="query.validation",
    )


def _combined_support_status(*assessments: SupportAssessment) -> SupportStatus:
    statuses = {assessment.status for assessment in assessments}
    if SupportStatus.UNSUPPORTED in statuses:
        return SupportStatus.UNSUPPORTED
    if SupportStatus.WEAK_SUPPORT in statuses:
        return SupportStatus.WEAK_SUPPORT
    return SupportStatus.SUPPORTED


def _query_value(
    *,
    specification: AnalysisSpecification,
    query_index: int,
    means: np.ndarray,
    quantiles: np.ndarray,
    risks: np.ndarray,
) -> tuple[str, float]:
    query = specification.queries[query_index]
    x_index = exact_grid_index(specification.intervention_grid, query.x)
    if query.kind == "mean":
        return "interventional_mean", float(means[x_index])
    if query.kind == "quantile":
        if query.level is None:
            raise ValueError("A quantile query requires level.")
        level_index = exact_grid_index(specification.quantile_levels, query.level)
        return "interventional_quantile", float(quantiles[x_index, level_index])
    if query.kind == "risk":
        if query.threshold is None:
            raise ValueError("A risk query requires threshold.")
        threshold_index = exact_grid_index(specification.risk_thresholds, query.threshold)
        return "threshold_risk", float(risks[x_index, threshold_index])
    if query.comparison_x is None:
        raise ValueError(f"A {query.kind} query requires comparison_x.")
    comparison_index = exact_grid_index(specification.intervention_grid, query.comparison_x)
    if query.kind == "mean_contrast":
        return "mean_contrast_x_minus_comparison_x", float(means[x_index] - means[comparison_index])
    if query.kind == "quantile_contrast":
        if query.level is None:
            raise ValueError("A quantile contrast requires level.")
        level_index = exact_grid_index(specification.quantile_levels, query.level)
        return (
            "quantile_contrast_x_minus_comparison_x",
            float(quantiles[x_index, level_index] - quantiles[comparison_index, level_index]),
        )
    if query.kind == "risk_contrast":
        if query.threshold is None:
            raise ValueError("A risk contrast requires threshold.")
        threshold_index = exact_grid_index(specification.risk_thresholds, query.threshold)
        return (
            "risk_contrast_x_minus_comparison_x",
            float(risks[x_index, threshold_index] - risks[comparison_index, threshold_index]),
        )
    raise ValueError(f"Unsupported query kind: {query.kind}")


def predict_backend(
    backend: StatisticalBackend,
    stage: str,
    features: np.ndarray,
    target: np.ndarray,
    prediction_features: np.ndarray | None = None,
    y_grid: np.ndarray | None = None,
) -> tuple[tuple[np.ndarray, ...], int, tuple[tuple[str, str], ...]]:
    """Fit and predict one stage; return arrays and counters, never fitted models."""
    before = backend.fit_calls
    if stage == "stage1":
        model = backend.fit_distribution(features, target)
        predictions = (model.cdf(features, target, paired=True),)
    elif stage == "stage2":
        shared_fit = getattr(backend, "fit_mean_distribution", None)
        if callable(shared_fit):
            mean_model, distribution_model = shared_fit(features, target)
        else:
            mean_model = backend.fit_mean(features, target)
            distribution_model = backend.fit_distribution(features, target)
        predictions = (
            mean_model.predict(prediction_features),
            distribution_model.cdf(prediction_features, y_grid, paired=False),
        )
    else:
        raise ValueError(f"Unknown prediction stage: {stage}")
    return predictions, backend.fit_calls - before, tuple(getattr(backend, "audit_details", ()))


def compute_predictions(arrays, specification, backend, run_id, audit, prediction_runner):
    """Compute predictions without rendering or writing artifacts; never return models."""
    roles = specification.roles
    z = arrays[roles.instrument]
    x = arrays[roles.treatment]
    y = arrays[roles.outcome]
    predictions, stage1_fits, _ = prediction_runner(backend, "stage1", z.reshape(-1, 1), x)
    control_rank = np.clip(predictions[0], 0.0, 1.0)
    audit.append(
        event_type="stage1_completed",
        stage="tabcf_iv.stage1",
        status="completed",
        run_id=run_id,
    )

    diagnostics, diagnostic_warnings = compute_diagnostics(z, x, y, control_rank)
    support = assess_support(x, control_rank, specification.intervention_grid)
    unsupported_grid = tuple(
        assessment for assessment in support if assessment.status is SupportStatus.UNSUPPORTED
    )
    if unsupported_grid:
        audit.append(
            event_type="outside_support_blocked",
            stage="tabcf_iv.support",
            status="blocked_before_stage2",
            run_id=run_id,
            details=(("unsupported_grid_count", str(len(unsupported_grid))),),
        )
        raise DCFAError(
            ErrorCode.OUTSIDE_SUPPORT,
            "The strict intervention grid contains unsupported values; no Stage 2 fit or "
            "causal numerical output was produced.",
            stage="support.validation",
            context={
                "unsupported_interventions": [
                    {
                        "x": assessment.x,
                        "coverage_score": assessment.coverage_score,
                        "reason": assessment.reason,
                    }
                    for assessment in unsupported_grid
                ]
            },
        )
    for query in specification.queries:
        query_support = [_support_for_x(support, query.x)]
        if query.comparison_x is not None:
            query_support.append(_support_for_x(support, query.comparison_x))
        if _combined_support_status(*query_support) is SupportStatus.UNSUPPORTED:
            audit.append(
                event_type="outside_support_blocked",
                stage="tabcf_iv.support",
                status="blocked",
                run_id=run_id,
                details=(("query_id", query.query_id),),
            )
            raise DCFAError(
                ErrorCode.OUTSIDE_SUPPORT,
                "A requested intervention is outside supported regions; no causal "
                "numerical claim was produced.",
                stage="support.validation",
                context={
                    "query_id": query.query_id,
                    "x": query.x,
                    "comparison_x": query.comparison_x,
                },
            )

    stage2_features = np.column_stack([x, control_rank])
    x_grid = np.asarray(specification.intervention_grid, dtype=float)
    y_min = float(np.min(y))
    y_max = float(np.max(y))
    y_span = max(y_max - y_min, 1.0)
    y_lower = min([y_min - 0.35 * y_span, *specification.risk_thresholds])
    y_upper = max([y_max + 0.35 * y_span, *specification.risk_thresholds])
    y_grid = np.linspace(y_lower, y_upper, 161)
    v_nodes, v_weights = np.polynomial.legendre.leggauss(18)
    v_grid = 0.5 * (v_nodes + 1.0)
    weights = 0.5 * v_weights

    batched_features = np.concatenate(
        [np.column_stack([np.full(len(v_grid), intervention), v_grid]) for intervention in x_grid],
        axis=0,
    )
    predictions, stage2_fits, backend_audit_details = prediction_runner(
        backend, "stage2", stage2_features, y, batched_features, y_grid
    )
    audit.append(
        event_type="stage2_completed",
        stage="tabcf_iv.stage2",
        status="completed",
        run_id=run_id,
    )

    conditional_means = predictions[0].reshape(len(x_grid), len(v_grid))
    means = np.tensordot(conditional_means, weights, axes=([1], [0]))
    conditional_cdf = predictions[1].reshape(len(x_grid), len(v_grid), len(y_grid))
    cdf = np.tensordot(conditional_cdf, weights, axes=([1], [0]))
    cdf = canonicalize_cdf(cdf)
    quantiles = invert_cdf(cdf, y_grid, specification.quantile_levels)
    risks = interpolate_risks(cdf, y_grid, specification.risk_thresholds)

    return (
        x_grid,
        y_grid,
        means,
        cdf,
        quantiles,
        risks,
        diagnostics,
        diagnostic_warnings,
        support,
        stage1_fits + stage2_fits,
        backend_audit_details,
        audit,
    )


class TabCFAnalysisEngine:
    """Runs the validated vertical slice and serves cached ordinary follow-ups."""

    def __init__(
        self,
        *,
        backend_factory: BackendFactory = _default_backend_factory,
        cache: ResultCache | None = None,
        prediction_runner: Callable = predict_backend,
    ) -> None:
        self.prediction_runner = prediction_runner
        self.backend_factory = backend_factory
        self.cache = cache or ResultCache()

    def _cache_key(self, specification: AnalysisSpecification) -> str:
        return content_id(
            "cache",
            {
                "specification_id": specification.specification_id,
                "dataset_hash": specification.dataset_hash,
                "backend": specification.estimator_backend.value,
                "profile": specification.execution_profile.value,
            },
        )

    def analyze(
        self,
        data: Mapping[str, np.ndarray],
        specification: AnalysisSpecification,
        dataset_manifest: DatasetManifest,
        *,
        output_dir: Path | None = None,
    ) -> AnalysisRun:
        # These gates intentionally precede backend construction and every fit.
        validate_tabcf_specification(specification)
        arrays = validate_tabcf_data(data, specification)
        validate_tabcf_dataset_manifest(dataset_manifest, specification, arrays)
        cache_key = self._cache_key(specification)
        cached = self.cache.get(cache_key)
        if cached is not None:
            bundle, ledger = cached
            audit = AuditTrail(
                specification_id=specification.specification_id,
                track=specification.track,
                execution_profile=specification.execution_profile,
                estimator_backend=specification.estimator_backend,
                evidence_status=specification.evidence_status,
            )
            audit.append(
                event_type="cache_hit",
                stage="cache.lookup",
                status="completed_without_refit",
                run_id=bundle.run_id,
            )
            manifest = RunManifest(
                run_id=bundle.run_id,
                specification_id=bundle.specification_id,
                dataset_hash=bundle.dataset_hash,
                backend_manifest_id="cached",
                track=bundle.track,
                execution_profile=bundle.execution_profile,
                estimator_backend=bundle.estimator_backend,
                evidence_status=bundle.evidence_status,
                seed=specification.seed,
            )
            return AnalysisRun(bundle, ledger, audit, manifest, (), 0)

        require_fresh_output_directory(output_dir)

        audit = AuditTrail(
            specification_id=specification.specification_id,
            track=specification.track,
            execution_profile=specification.execution_profile,
            estimator_backend=specification.estimator_backend,
            evidence_status=specification.evidence_status,
        )
        audit.append(
            event_type="specification_validated",
            stage="specification",
            status="completed",
        )
        backend = self.backend_factory(specification)
        if (
            backend.name != specification.estimator_backend
            or backend.execution_profile != specification.execution_profile
            or backend.evidence_status != specification.evidence_status
        ):
            raise DCFAError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Constructed backend identity does not match the immutable specification.",
                stage="backend.selection",
            )
        backend_manifest = backend.manifest
        manifest_markers = (
            backend_manifest.track,
            backend_manifest.execution_profile,
            backend_manifest.estimator_backend,
            backend_manifest.evidence_status,
        )
        specification_markers = (
            specification.track,
            specification.execution_profile,
            specification.estimator_backend,
            specification.evidence_status,
        )
        if manifest_markers != specification_markers:
            raise DCFAError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Backend manifest markers do not match the immutable specification.",
                stage="backend.selection",
            )
        if backend_manifest.dcfa_source_tree_hash != dcfa_source_tree_hash():
            raise DCFAError(
                ErrorCode.HASH_MISMATCH,
                "Backend manifest does not bind the currently executing DCFA source tree.",
                stage="backend.selection",
            )
        run_id = content_id(
            "run",
            {
                "specification_id": specification.specification_id,
                "dataset_hash": specification.dataset_hash,
                "backend_manifest_id": backend_manifest.backend_manifest_id,
            },
        )

        (
            x_grid,
            y_grid,
            means,
            cdf,
            quantiles,
            risks,
            diagnostics,
            diagnostic_warnings,
            support,
            backend_fit_calls,
            backend_audit_details,
            audit,
        ) = compute_predictions(
            arrays, specification, backend, run_id, audit, self.prediction_runner
        )

        global_warnings: list[WarningRecord] = []
        development_assumption: str | None = None
        if backend.name is EstimatorBackend.SKLEARN_QUANTILE_FALLBACK:
            global_warnings.append(
                WarningRecord(
                    code="DEVELOPMENT_FALLBACK_NOT_TABCF",
                    message=(
                        "This explicitly selected sklearn fallback validates engineering data "
                        "flow only; "
                        "it is not TabCF and is ineligible for locked Track T claims."
                    ),
                    severity=WarningSeverity.WARNING,
                    source="backend.contract",
                )
            )
            development_assumption = (
                "The local sklearn fallback is an engineering approximation and not the "
                "TabCF estimator."
            )
        elif backend.evidence_status.value == "development_only":
            global_warnings.append(
                WarningRecord(
                    code="DEVELOPMENT_TABPFN_NOT_RELEASE_ELIGIBLE",
                    message=(
                        "This TabPFN-backed managed/local run is development-only, not a "
                        "hash-locked Track T result, and is ineligible for release claims."
                    ),
                    severity=WarningSeverity.WARNING,
                    source="backend.contract",
                )
            )
            if is_sha256_digest(backend_manifest.model_artifact_hash):
                development_assumption = (
                    "Local TabPFN v2 uses the recorded checkpoint artifact, but the current "
                    "runtime image is not release-locked and cannot enter locked Track T evidence."
                )
            elif (
                backend_manifest.model_artifact_hash
                == "managed_service_checkpoint_not_locally_available"
            ):
                development_assumption = (
                    "Managed-service TabPFN is service-version-traceable rather than bitwise "
                    "reproducible and cannot enter locked Track T evidence."
                )
            else:
                development_assumption = (
                    "This TabPFN development profile is recorded in the backend manifest and "
                    "cannot enter locked Track T evidence."
                )
        global_warnings.extend(diagnostic_warnings)
        if any(item.status is SupportStatus.WEAK_SUPPORT for item in support):
            global_warnings.append(
                WarningRecord(
                    code="WEAK_INTERVENTION_SUPPORT",
                    message="At least one intervention has weak empirical joint support.",
                    severity=WarningSeverity.WARNING,
                    source="support.assessment",
                )
            )
        distribution = None
        if specification.distribution is not None:
            from dcfa.tabcf_iv.distribution import derive_distribution

            distribution = derive_distribution(
                specification.distribution, y_grid, cdf, quantiles, risks
            )
            global_warnings.append(
                WarningRecord(
                    code="DISTRIBUTIONAL_POINT_ESTIMATES",
                    message="Point estimates only, without confidence intervals or significance. "
                    "Quantile changes are distributional, not individual effects. "
                    "CDFs cover only the evaluated outcome grid; no extrapolation.",
                    severity=WarningSeverity.WARNING,
                    source="distribution.presentation",
                )
            )
            if specification.roles.outcome == "log_packs_per_capita":
                global_warnings.append(
                    WarningRecord(
                        code="POOLED_STATE_YEAR_LIMITATIONS",
                        message="Real-data exploratory state-year aggregates with equal "
                        "observation "
                        "weights, repeated states, and omitted income and state/year effects. "
                        "Within-state dependence and omitted confounding are not addressed. "
                        "Instrument exclusion and exogeneity remain assumptions.",
                        severity=WarningSeverity.WARNING,
                        source="distribution.presentation",
                    )
                )
            if distribution["boundary_limited"]:
                global_warnings.append(
                    WarningRecord(
                        code="QUANTILE_GRID_ENDPOINT",
                        message="At least one quantile touches an evaluated-grid endpoint. "
                        "Boundary-limited quantiles are clipped descriptions; restrict "
                        "tail conclusions and do not extrapolate.",
                        severity=WarningSeverity.WARNING,
                        source="distribution.presentation",
                    )
                )
        warnings = tuple(global_warnings)
        assumptions = (
            (
                "One continuous treatment, one continuous outcome, one scalar instrument, "
                "and no baseline covariates W."
            ),
            (
                "Relevance, exclusion, instrument exogeneity, scalar monotonicity, and common "
                "support are assumptions; empirical diagnostics do not prove them."
            ),
            *((development_assumption,) if development_assumption is not None else ()),
        )

        if backend_audit_details:
            audit.append(
                event_type="managed_service_observed",
                stage="backend.provenance",
                status="completed",
                run_id=run_id,
                details=tuple(backend_audit_details),
            )

        numerical_core = {
            "track": specification.track,
            "execution_profile": specification.execution_profile,
            "estimator_backend": specification.estimator_backend,
            "evidence_status": specification.evidence_status,
            "run_id": run_id,
            "specification_id": specification.specification_id,
            "dataset_hash": specification.dataset_hash,
            "x_grid": x_grid,
            "y_grid": y_grid,
            "interventional_cdf": cdf,
            "interventional_mean": means,
            "quantile_levels": specification.quantile_levels,
            "interventional_quantiles": quantiles,
            "risk_thresholds": specification.risk_thresholds,
            "interventional_risks": risks,
            "diagnostics": diagnostics,
            "support": support,
            "warnings": warnings,
            "assumptions": assumptions,
        }
        if distribution is not None:
            numerical_core["distribution"] = distribution
        source_artifact = "numerical_core.json"
        if output_dir is None:
            source_artifact_hash = sha256_digest(numerical_core)
        else:
            core_path = output_dir / source_artifact
            _write_json(core_path, numerical_core)
            source_artifact_hash = file_sha256(core_path)
        bundle_id = content_id("bundle", numerical_core)

        records: list[EvidenceRecord] = []
        provisional_queries: list[
            tuple[int, str, float, SupportStatus, tuple[WarningRecord, ...]]
        ] = []
        query_specs = specification.queries
        if distribution is not None:
            query_specs = tuple(
                QuerySpecification(
                    query_id=m["key"],
                    kind="distribution",
                    x=specification.intervention_grid[1],
                    comparison_x=specification.intervention_grid[0],
                    units=m["units"],
                )
                for m in distribution["metrics"]
            )
        for query_index, query in enumerate(query_specs):
            claim_type, value = (
                ("distribution:" + query.query_id, distribution["metrics"][query_index]["value"])
                if distribution is not None
                else _query_value(
                    specification=specification,
                    query_index=query_index,
                    means=means,
                    quantiles=quantiles,
                    risks=risks,
                )
            )
            assessments = [_support_for_x(support, query.x)]
            if query.comparison_x is not None:
                assessments.append(_support_for_x(support, query.comparison_x))
            status = _combined_support_status(*assessments)
            query_warnings = warnings
            display = format(value, ".6g")
            record = build_evidence_record(
                track=specification.track,
                evidence_status=specification.evidence_status,
                estimator_backend=specification.estimator_backend,
                execution_profile=specification.execution_profile,
                run_id=run_id,
                dataset_hash=specification.dataset_hash,
                specification_id=specification.specification_id,
                result_bundle_id=bundle_id,
                claim_type=claim_type,
                value_raw=value,
                value_display=display,
                units=query.units,
                support_status=status,
                warnings=query_warnings,
                source_artifact=source_artifact,
                source_artifact_hash=source_artifact_hash,
            )
            records.append(record)
            provisional_queries.append((query_index, claim_type, value, status, query_warnings))

        ledger = EvidenceLedger(records)
        query_results = tuple(
            QueryResult(
                query_id=query_specs[index].query_id,
                claim_type=claim_type,
                value_raw=value,
                value_display=format(value, ".6g"),
                units=query_specs[index].units,
                support_status=status,
                warnings=query_warnings,
                evidence_id=records[position].evidence_id,
            )
            for position, (index, claim_type, value, status, query_warnings) in enumerate(
                provisional_queries
            )
        )
        bundle = ResultBundle(
            result_bundle_id=bundle_id,
            run_id=run_id,
            specification_id=specification.specification_id,
            dataset_hash=specification.dataset_hash,
            track=specification.track,
            execution_profile=specification.execution_profile,
            estimator_backend=specification.estimator_backend,
            evidence_status=specification.evidence_status,
            x_grid=tuple(float(value) for value in x_grid),
            y_grid=tuple(float(value) for value in y_grid),
            distribution=distribution,
            interventional_cdf=tuple(tuple(float(value) for value in row) for row in cdf),
            interventional_mean=tuple(float(value) for value in means),
            quantile_levels=specification.quantile_levels,
            interventional_quantiles=tuple(
                tuple(float(value) for value in row) for row in quantiles
            ),
            risk_thresholds=specification.risk_thresholds,
            interventional_risks=tuple(tuple(float(value) for value in row) for row in risks),
            diagnostics=diagnostics,
            support=support,
            warnings=warnings,
            assumptions=assumptions,
            queries=query_results,
            source_artifact=source_artifact,
            source_artifact_hash=source_artifact_hash,
        )
        validate_bundle_evidence(bundle, ledger)
        self.cache.put(cache_key, bundle, ledger)
        audit.append(
            event_type="evidence_validated",
            stage="evidence.validation",
            status="completed",
            run_id=run_id,
            details=(("evidence_count", str(len(records))),),
        )

        artifact_paths: dict[str, Path] = {}
        artifact_hashes: tuple[tuple[str, str], ...] = ()
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            artifact_paths["numerical_core"] = output_dir / source_artifact
            artifact_paths["specification"] = output_dir / "specification.json"
            artifact_paths["dataset_manifest"] = output_dir / "dataset_manifest.json"
            artifact_paths["backend_manifest"] = output_dir / "backend_manifest.json"
            artifact_paths["evidence"] = output_dir / "evidence_records.jsonl"
            artifact_paths["result_bundle"] = output_dir / "result_bundle.json"
            artifact_paths["audit"] = output_dir / "audit.jsonl"
            artifact_paths["report"] = output_dir / "report.md"
            artifact_paths["plot"] = output_dir / "interventional_summary.png"
            _write_json(artifact_paths["specification"], specification)
            _write_json(artifact_paths["dataset_manifest"], dataset_manifest)
            _write_json(artifact_paths["backend_manifest"], backend_manifest)
            _write_jsonl(artifact_paths["evidence"], ledger.records())
            _write_json(artifact_paths["result_bundle"], bundle)
            _write_jsonl(artifact_paths["audit"], audit.events())
            _atomic_write(
                artifact_paths["report"],
                render_markdown_report(bundle, ledger, backend_manifest=backend_manifest).encode(
                    "utf-8"
                ),
            )
            render_bundle_plot(bundle, ledger, artifact_paths["plot"])
            artifact_paths["report_manifest"] = output_dir / "report_manifest.json"
            _write_json(
                artifact_paths["report_manifest"],
                {
                    "track": specification.track,
                    "execution_profile": specification.execution_profile,
                    "estimator_backend": specification.estimator_backend,
                    "evidence_status": specification.evidence_status,
                    "result_bundle_id": bundle.result_bundle_id,
                    "evidence_ids": tuple(query.evidence_id for query in bundle.queries),
                    "report_hash": file_sha256(artifact_paths["report"]),
                    "plot_hash": file_sha256(artifact_paths["plot"]),
                    "source_artifact": bundle.source_artifact,
                    "source_artifact_hash": bundle.source_artifact_hash,
                },
            )
            if bundle.distribution is not None:
                from dcfa.distribution_reporting import export_distribution

                artifact_paths["distribution_results.json"] = (
                    output_dir / "distribution_results.json"
                )
                _write_json(
                    artifact_paths["distribution_results.json"], export_distribution(bundle, ledger)
                )
            artifact_hashes = tuple(
                sorted((name, file_sha256(path)) for name, path in artifact_paths.items())
            )

        run_manifest = RunManifest(
            run_id=run_id,
            specification_id=specification.specification_id,
            dataset_hash=specification.dataset_hash,
            backend_manifest_id=backend_manifest.backend_manifest_id,
            track=specification.track,
            execution_profile=specification.execution_profile,
            estimator_backend=specification.estimator_backend,
            evidence_status=specification.evidence_status,
            seed=specification.seed,
            artifact_hashes=artifact_hashes,
        )
        if output_dir is not None:
            artifact_paths["run_manifest"] = output_dir / "run_manifest.json"
            _write_json(artifact_paths["run_manifest"], run_manifest)

        return AnalysisRun(
            bundle=bundle,
            ledger=ledger,
            audit=audit,
            run_manifest=run_manifest,
            artifact_paths=tuple(sorted(artifact_paths.items())),
            backend_fit_calls=backend_fit_calls,
        )

    def follow_up(self, specification: AnalysisSpecification, query_id: str) -> QueryResult:
        cached = self.cache.get(self._cache_key(specification))
        if cached is None:
            raise DCFAError(
                ErrorCode.STALE_ID,
                "No validated cached bundle exists for this specification.",
                stage="cache.follow_up",
            )
        bundle, ledger = cached
        validate_bundle_evidence(bundle, ledger)
        for query in bundle.queries:
            if query.query_id == query_id:
                return query
        raise DCFAError(
            ErrorCode.STALE_ID,
            f"Query ID {query_id} is not present in the cached bundle.",
            stage="cache.follow_up",
            context={"query_id": query_id},
        )
