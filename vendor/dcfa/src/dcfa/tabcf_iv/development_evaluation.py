"""Oracle-scored engineering evaluation for the non-paper local IV fixture."""

from __future__ import annotations

import importlib.metadata
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.special import ndtr, ndtri

from dcfa import __version__
from dcfa.audit import AuditTrail
from dcfa.canonical import canonical_json_bytes, content_id, file_sha256, sha256_digest
from dcfa.constants import (
    EstimatorBackend,
    EvidenceStatus,
    ExecutionProfile,
    SupportStatus,
    Track,
    WarningSeverity,
)
from dcfa.evidence import (
    EvidenceLedger,
    build_evidence_record,
    validate_track_t_development_evidence,
)
from dcfa.output import require_fresh_output_directory
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.schemas import (
    EvidenceRecord,
    RunManifest,
    TrackTDevelopmentEvaluationBundle,
    TrackTEvaluationEstimate,
    WarningRecord,
)
from dcfa.tabcf_iv.development_dgp import generate_development_iv
from dcfa.tabcf_iv.development_specification import development_specification
from dcfa.tabcf_iv.pipeline import TabCFAnalysisEngine

_METRIC_UNITS = {
    "cdf_rmse": "cdf_probability",
    "mean_rmse": "Y_units",
    "quantile_rmse": "Y_units",
    "risk_rmse": "probability",
    "empirical_warning_rate": "proportion",
}


@dataclass(frozen=True)
class DevelopmentEvaluationReplication:
    scenario: str
    seed: int
    dataset_hash: str
    cdf_rmse: float
    mean_rmse: float
    quantile_rmse: float
    risk_rmse: float
    empirical_warning_rate: float
    result_bundle_id: str


@dataclass(frozen=True)
class TrackTDevelopmentEvaluationRun:
    bundle: TrackTDevelopmentEvaluationBundle
    ledger: EvidenceLedger
    audit: AuditTrail
    run_manifest: RunManifest
    replications: tuple[DevelopmentEvaluationReplication, ...]
    artifact_paths: tuple[tuple[str, Path], ...]


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
    _atomic_write(path, b"\n".join(canonical_json_bytes(value) for value in values) + b"\n")


def _oracle_components(bundle, threshold: float) -> tuple[np.ndarray, ...]:
    x_grid = np.asarray(bundle.x_grid)
    y_grid = np.asarray(bundle.y_grid)
    mean = 0.8 + 1.4 * x_grid + 0.25 * x_grid**2
    standard_deviation = float(np.sqrt(0.9**2 + 0.6**2))
    cdf = ndtr((y_grid[None, :] - mean[:, None]) / standard_deviation)
    quantiles = mean[:, None] + standard_deviation * ndtri(
        np.asarray(bundle.quantile_levels)[None, :]
    )
    risks = ndtr((float(threshold) - mean) / standard_deviation)[:, None]
    return cdf, mean, quantiles, risks


def _evaluate_replication(scenario: str, seed: int, rows: int) -> DevelopmentEvaluationReplication:
    strength = 1.6 if scenario == "strong_iv" else 0.02
    dataset = generate_development_iv(n=rows, seed=seed, instrument_strength=strength)
    x_values = tuple(
        float(value) for value in np.quantile(dataset.columns["X"], [0.1, 0.3, 0.5, 0.7, 0.9])
    )
    threshold = float(np.median(dataset.columns["Y"]))
    specification = development_specification(
        dataset_hash=dataset.manifest.dataset_hash,
        x_values=x_values,
        outcome_threshold=threshold,
        seed=seed,
    )
    run = TabCFAnalysisEngine().analyze(dataset.columns, specification, dataset.manifest)
    oracle_cdf, oracle_mean, oracle_quantiles, oracle_risks = _oracle_components(
        run.bundle, threshold
    )
    warning_triggered = float(
        any("WEAK_FIRST_STAGE" in warning.code for warning in run.bundle.warnings)
    )
    return DevelopmentEvaluationReplication(
        scenario=scenario,
        seed=seed,
        dataset_hash=dataset.manifest.dataset_hash,
        cdf_rmse=float(
            np.sqrt(np.mean((np.asarray(run.bundle.interventional_cdf) - oracle_cdf) ** 2))
        ),
        mean_rmse=float(
            np.sqrt(np.mean((np.asarray(run.bundle.interventional_mean) - oracle_mean) ** 2))
        ),
        quantile_rmse=float(
            np.sqrt(
                np.mean((np.asarray(run.bundle.interventional_quantiles) - oracle_quantiles) ** 2)
            )
        ),
        risk_rmse=float(
            np.sqrt(np.mean((np.asarray(run.bundle.interventional_risks) - oracle_risks) ** 2))
        ),
        empirical_warning_rate=warning_triggered,
        result_bundle_id=run.bundle.result_bundle_id,
    )


def _render_report(bundle: TrackTDevelopmentEvaluationBundle) -> str:
    lines = [
        "# Track T fallback engineering benchmark",
        "",
        f"- data_label: `{bundle.data_label}`",
        f"- execution_profile: `{bundle.execution_profile.value}`",
        f"- estimator_backend: `{bundle.estimator_backend.value}`",
        f"- evidence_status: `{bundle.evidence_status.value}`",
        "",
        (
            "This evaluates a local sklearn approximation on a DCFA-only fixture. It is not "
            "TabCF, is not mapped to manuscript DGP codes, and cannot support Track T claims."
        ),
        "",
        "| Scenario | Metric | Mean | Seed-level SE | Evidence |",
        "|---|---|---:|---:|---|",
    ]
    lines.extend(
        f"| {estimate.scenario} | {estimate.metric} | {estimate.value_display} | "
        f"{estimate.standard_error:.6g} | `{estimate.evidence_id}` |"
        for estimate in bundle.values
    )
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- `{warning.code}`: {warning.message}" for warning in bundle.warnings)
    lines.extend(["", "## Assumptions", ""])
    lines.extend(f"- {assumption}" for assumption in bundle.assumptions)
    return "\n".join(lines) + "\n"


def run_development_evaluation(
    *,
    seeds: tuple[int, ...],
    rows: int,
    output_dir: Path | None = None,
) -> TrackTDevelopmentEvaluationRun:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Development evaluation seeds must be non-empty and unique.")
    require_fresh_output_directory(output_dir)
    backend_manifest = {
        "track": Track.TABCF_IV,
        "execution_profile": ExecutionProfile.LOCAL_DEVELOPMENT,
        "estimator_backend": EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        "evidence_status": EvidenceStatus.DEVELOPMENT_ONLY,
        "protocol_version": "track_t_development_evaluation_v5",
        "tool_version": __version__,
        "dcfa_source_tree_hash": dcfa_source_tree_hash(),
        "package_versions": (
            ("numpy", importlib.metadata.version("numpy")),
            ("scikit-learn", importlib.metadata.version("scikit-learn")),
        ),
        "backend_contract": "fixed_hist_gradient_boosting_quantile_grid",
    }
    backend_manifest_id = content_id("backend", backend_manifest)
    specification = {
        "track": Track.TABCF_IV,
        "execution_profile": ExecutionProfile.LOCAL_DEVELOPMENT,
        "estimator_backend": EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        "evidence_status": EvidenceStatus.DEVELOPMENT_ONLY,
        "data_label": "fallback_engineering_benchmark_not_tabcf",
        "dgp_label": "dcfa_development_triangular_iv_v1",
        "dgp_mapping_status": "not_mapped_to_tabcf_manuscript_codes",
        "scenarios": ("strong_iv", "weak_iv"),
        "seeds": seeds,
        "rows": rows,
        "backend_manifest_id": backend_manifest_id,
        "version": "track_t_development_evaluation_v5",
    }
    specification_id = content_id("track_t_dev_spec", specification)
    audit = AuditTrail(
        specification_id=specification_id,
        track=Track.TABCF_IV,
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
    )
    audit.append(
        event_type="development_protocol_validated",
        stage="track_t.development_evaluation",
        status="explicitly_not_release_eligible",
    )
    replications = tuple(
        _evaluate_replication(scenario, seed, rows)
        for scenario in ("strong_iv", "weak_iv")
        for seed in seeds
    )
    dataset_hash = sha256_digest(tuple(result.dataset_hash for result in replications))
    run_id = content_id(
        "track_t_dev_run",
        {
            "specification_id": specification_id,
            "replication_bundle_ids": tuple(result.result_bundle_id for result in replications),
            "backend_manifest_id": backend_manifest_id,
        },
    )
    warnings = (
        WarningRecord(
            code="DEVELOPMENT_FALLBACK_NOT_TABCF",
            message=(
                "These oracle errors validate an sklearn engineering approximation only; "
                "they are ineligible for locked Track T results."
            ),
            severity=WarningSeverity.WARNING,
            source="track_t.development_evaluation",
        ),
        WarningRecord(
            code="DGP_NOT_MAPPED_TO_MANUSCRIPT",
            message="The local fixture has no frozen mapping to TabCF manuscript DGP codes.",
            severity=WarningSeverity.WARNING,
            source="track_t.development_evaluation",
        ),
    )
    assumptions = (
        "The oracle follows the exact DCFA development fixture, not a manuscript DGP.",
        "Seed-level variation is engineering evidence and not a confidence interval.",
    )
    numerical_core = {
        **specification,
        "specification_id": specification_id,
        "run_id": run_id,
        "dataset_hash": dataset_hash,
        "replications": replications,
        "warnings": warnings,
        "assumptions": assumptions,
    }
    source_artifact = "numerical_core.json"
    if output_dir is None:
        source_hash = sha256_digest(numerical_core)
    else:
        _write_json(output_dir / source_artifact, numerical_core)
        source_hash = file_sha256(output_dir / source_artifact)
    bundle_id = content_id("track_t_dev_bundle", numerical_core)
    records: list[EvidenceRecord] = []
    estimates: list[TrackTEvaluationEstimate] = []
    for scenario in ("strong_iv", "weak_iv"):
        scenario_rows = tuple(result for result in replications if result.scenario == scenario)
        for metric, units in _METRIC_UNITS.items():
            values = np.asarray([float(getattr(result, metric)) for result in scenario_rows])
            mean = float(np.mean(values))
            standard_error = (
                0.0 if len(values) == 1 else float(np.std(values, ddof=1) / np.sqrt(len(values)))
            )
            display = format(mean, ".6g")
            record = build_evidence_record(
                track=Track.TABCF_IV,
                evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
                estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
                execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
                run_id=run_id,
                dataset_hash=dataset_hash,
                specification_id=specification_id,
                result_bundle_id=bundle_id,
                claim_type=f"development_oracle_metric:{scenario}:{metric}",
                value_raw=mean,
                value_display=display,
                units=units,
                support_status=SupportStatus.SUPPORTED,
                warnings=warnings,
                source_artifact=source_artifact,
                source_artifact_hash=source_hash,
            )
            records.append(record)
            estimates.append(
                TrackTEvaluationEstimate(
                    scenario=scenario,
                    metric=metric,
                    seed_count=len(values),
                    value_raw=mean,
                    standard_error=standard_error,
                    value_display=display,
                    units=units,
                    evidence_id=record.evidence_id,
                )
            )
    ledger = EvidenceLedger(records)
    bundle = TrackTDevelopmentEvaluationBundle(
        result_bundle_id=bundle_id,
        run_id=run_id,
        specification_id=specification_id,
        dataset_hash=dataset_hash,
        track=Track.TABCF_IV,
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
        data_label="fallback_engineering_benchmark_not_tabcf",
        values=tuple(estimates),
        warnings=warnings,
        assumptions=assumptions,
        source_artifact=source_artifact,
        source_artifact_hash=source_hash,
    )
    validate_track_t_development_evidence(bundle, ledger)
    audit.append(
        event_type="development_metrics_completed",
        stage="track_t.development_evaluation",
        status="completed_development_only",
        run_id=run_id,
        details=(("evidence_count", str(len(records))),),
    )

    artifact_paths: list[tuple[str, Path]] = []
    artifact_hashes: list[tuple[str, str]] = []
    if output_dir is not None:
        dataset_manifest = {
            "track": Track.TABCF_IV,
            "execution_profile": ExecutionProfile.LOCAL_DEVELOPMENT,
            "estimator_backend": EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
            "evidence_status": EvidenceStatus.DEVELOPMENT_ONLY,
            "dataset_hash": dataset_hash,
            "replication_dataset_hashes": tuple(result.dataset_hash for result in replications),
            "source_kind": "synthetic_development_fixture",
        }
        report_manifest = {
            "track": Track.TABCF_IV,
            "execution_profile": ExecutionProfile.LOCAL_DEVELOPMENT,
            "estimator_backend": EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
            "evidence_status": EvidenceStatus.DEVELOPMENT_ONLY,
            "result_bundle_id": bundle.result_bundle_id,
            "evidence_ids": tuple(record.evidence_id for record in records),
            "report_logic": "pure_render_from_validated_track_t_development_bundle",
        }
        artifacts: tuple[tuple[str, str, object | bytes], ...] = (
            ("specification", "specification.json", specification),
            ("dataset_manifest", "dataset_manifest.json", dataset_manifest),
            ("backend_manifest", "backend_manifest.json", backend_manifest),
            ("numerical_core", source_artifact, numerical_core),
            ("result_bundle", "result_bundle.json", bundle),
            ("evidence", "evidence_records.jsonl", tuple(records)),
            ("audit", "audit.jsonl", audit.events()),
            ("report", "report.md", _render_report(bundle).encode("utf-8")),
            ("report_manifest", "report_manifest.json", report_manifest),
        )
        for key, filename, value in artifacts:
            path = output_dir / filename
            if isinstance(value, bytes):
                _atomic_write(path, value)
            elif filename.endswith(".jsonl"):
                _write_jsonl(path, value)  # type: ignore[arg-type]
            else:
                _write_json(path, value)
            artifact_paths.append((key, path))
            artifact_hashes.append((key, file_sha256(path)))
    run_manifest = RunManifest(
        run_id=run_id,
        specification_id=specification_id,
        dataset_hash=dataset_hash,
        backend_manifest_id=backend_manifest_id,
        track=Track.TABCF_IV,
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
        seed=seeds[0],
        artifact_hashes=tuple(artifact_hashes),
    )
    if output_dir is not None:
        path = output_dir / "run_manifest.json"
        _write_json(path, run_manifest)
        artifact_paths.append(("run_manifest", path))
    return TrackTDevelopmentEvaluationRun(
        bundle=bundle,
        ledger=ledger,
        audit=audit,
        run_manifest=run_manifest,
        replications=replications,
        artifact_paths=tuple(artifact_paths),
    )
