"""Evidence-producing runner for the four Track H semi-synthetic scenarios."""

from __future__ import annotations

import importlib.metadata
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dcfa import __version__
from dcfa.audit import AuditTrail
from dcfa.canonical import canonical_json_bytes, content_id, file_sha256, sha256_digest
from dcfa.constants import SupportStatus, WarningSeverity
from dcfa.evidence import (
    EvidenceLedger,
    build_evidence_record,
    validate_semisynthetic_bundle_evidence,
)
from dcfa.hillstrom_policy.contracts import HillstromDataset, SplitManifest
from dcfa.hillstrom_policy.data import validate_hillstrom_split
from dcfa.hillstrom_policy.semisynthetic import (
    SEMISYNTHETIC_SCENARIOS,
    SemiSyntheticMetrics,
    run_four_scenarios,
)
from dcfa.output import require_fresh_output_directory
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.schemas import (
    EvidenceRecord,
    RunManifest,
    SemiSyntheticEstimate,
    SemiSyntheticEvaluationBundle,
    WarningRecord,
)

_METRICS = (
    ("oracle_value", "two_week_net_spend_per_customer"),
    ("learned_policy_value", "two_week_net_spend_per_customer"),
    ("best_uniform_value", "two_week_net_spend_per_customer"),
    ("learned_regret", "two_week_net_spend_per_customer"),
    ("best_uniform_regret", "two_week_net_spend_per_customer"),
    ("optimal_action_accuracy", "proportion"),
    ("fallback_rate", "proportion"),
    ("abstention_coverage", "proportion"),
    ("selective_regret", "two_week_net_spend_per_customer"),
    ("fallback_inclusive_value", "two_week_net_spend_per_customer"),
    ("action_value_gap_mae", "two_week_net_spend_per_customer"),
    ("constraint_violations", "count"),
)


@dataclass(frozen=True)
class SemiSyntheticRun:
    bundle: SemiSyntheticEvaluationBundle
    ledger: EvidenceLedger
    audit: AuditTrail
    run_manifest: RunManifest
    replications: tuple[SemiSyntheticMetrics, ...]
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


def _render_report(bundle: SemiSyntheticEvaluationBundle) -> str:
    lines = [
        "# Track H semi-synthetic evaluation",
        "",
        f"- data_label: `{bundle.data_label}`",
        f"- track: `{bundle.track.value}`",
        f"- execution_profile: `{bundle.execution_profile.value}`",
        f"- estimator_backend: `{bundle.estimator_backend.value}`",
        f"- evidence_status: `{bundle.evidence_status.value}`",
        "",
        (
            "Oracle value, regret, and optimal-action accuracy are reported only because this "
            "track has a known simulated potential-outcome DGP. They are not real-RCT claims."
        ),
        "",
        "| Scenario | Metric | Mean | MC SE | Evidence |",
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


def run_semisynthetic_benchmark(
    dataset: HillstromDataset,
    split: SplitManifest,
    *,
    replications: int,
    row_count: int,
    seed: int,
    output_dir: Path | None = None,
) -> SemiSyntheticRun:
    require_fresh_output_directory(output_dir)
    validate_hillstrom_split(split, dataset)
    backend_manifest = {
        "track": dataset.manifest.track,
        "execution_profile": dataset.manifest.execution_profile,
        "estimator_backend": dataset.manifest.estimator_backend,
        "evidence_status": dataset.manifest.evidence_status,
        "protocol_version": "hillstrom_semisynthetic_v6",
        "tool_version": __version__,
        "dcfa_source_tree_hash": dcfa_source_tree_hash(),
        "package_versions": (
            ("numpy", importlib.metadata.version("numpy")),
            ("scikit-learn", importlib.metadata.version("scikit-learn")),
        ),
        "policy_model": "per_action_ridge_closed_form",
        "scenario_version": "hillstrom_semisynthetic_v6",
    }
    backend_manifest_id = content_id("backend", backend_manifest)
    specification = {
        "track": dataset.manifest.track,
        "execution_profile": dataset.manifest.execution_profile,
        "estimator_backend": dataset.manifest.estimator_backend,
        "evidence_status": dataset.manifest.evidence_status,
        "dataset_hash": dataset.manifest.dataset_hash,
        "split_manifest_id": split.split_manifest_id,
        "scenarios": SEMISYNTHETIC_SCENARIOS,
        "replications": replications,
        "row_count_per_replication": row_count,
        "seed": seed,
        "backend_manifest_id": backend_manifest_id,
        "version": "hillstrom_semisynthetic_v6",
    }
    specification_id = content_id("semisynth_spec", specification)
    audit = AuditTrail(
        specification_id=specification_id,
        track=dataset.manifest.track,
        execution_profile=dataset.manifest.execution_profile,
        estimator_backend=dataset.manifest.estimator_backend,
        evidence_status=dataset.manifest.evidence_status,
    )
    audit.append(
        event_type="source_covariates_locked",
        stage="hillstrom.semisynthetic",
        status="training_split_only",
        details=(("split_manifest_id", split.split_manifest_id),),
    )
    replications_raw = run_four_scenarios(
        dataset,
        split,
        replications=replications,
        row_count=row_count,
        seed=seed,
    )
    data_labels = {result.data_label for result in replications_raw}
    if len(data_labels) != 1:
        raise AssertionError("Semi-synthetic replications changed data labels.")
    data_label = next(iter(data_labels))
    warning = WarningRecord(
        code=(
            "DEVELOPMENT_NOT_HILLSTROM_CALIBRATED"
            if data_label != "hillstrom_calibrated_semisynthetic"
            else "SIMULATED_OUTCOMES_NOT_REAL_RCT"
        ),
        message=(
            "The covariate source is a development fixture, so these DGPs are not calibrated "
            "to real Hillstrom data."
            if data_label != "hillstrom_calibrated_semisynthetic"
            else "Potential outcomes are simulated; oracle metrics do not describe real customers."
        ),
        severity=WarningSeverity.WARNING,
        source="hillstrom.semisynthetic.boundary",
    )
    warnings = (warning,)
    assumptions = (
        "Only original training-split covariates are resampled.",
        "Action effects are prespecified and all three potential outcomes are simulated.",
        "Constrained policies are compared with the same-capacity oracle.",
        "Selective regret is row-wise regret versus the unconstrained best action among "
        "non-fallback decisions.",
        "Capacity truncation of learned comparators uses fitted action values, not oracle "
        "utilities.",
    )
    run_id = content_id(
        "semisynth_run",
        {
            "specification_id": specification_id,
            "replication_result_ids": tuple(result.result_id for result in replications_raw),
            "backend_manifest_id": backend_manifest_id,
        },
    )
    numerical_core = {
        **specification,
        "run_id": run_id,
        "specification_id": specification_id,
        "data_label": data_label,
        "replication_results": replications_raw,
        "warnings": warnings,
        "assumptions": assumptions,
    }
    source_artifact = "semisynthetic_numerical_core.json"
    if output_dir is None:
        source_hash = sha256_digest(numerical_core)
    else:
        _write_json(output_dir / source_artifact, numerical_core)
        source_hash = file_sha256(output_dir / source_artifact)
    bundle_id = content_id("semisynth_bundle", numerical_core)
    records: list[EvidenceRecord] = []
    estimates: list[SemiSyntheticEstimate] = []
    for scenario in SEMISYNTHETIC_SCENARIOS:
        scenario_rows = tuple(row for row in replications_raw if row.scenario == scenario)
        for metric, units in _METRICS:
            values = np.asarray([float(getattr(row, metric)) for row in scenario_rows])
            mean = float(np.mean(values))
            standard_error = (
                0.0 if len(values) == 1 else float(np.std(values, ddof=1) / np.sqrt(len(values)))
            )
            display = format(mean, ".6g")
            record = build_evidence_record(
                track=dataset.manifest.track,
                evidence_status=dataset.manifest.evidence_status,
                estimator_backend=dataset.manifest.estimator_backend,
                execution_profile=dataset.manifest.execution_profile,
                run_id=run_id,
                dataset_hash=dataset.manifest.dataset_hash,
                specification_id=specification_id,
                result_bundle_id=bundle_id,
                claim_type=f"semisynthetic:{scenario}:{metric}:replication_mean",
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
                SemiSyntheticEstimate(
                    scenario=scenario,
                    metric=metric,
                    replication_count=len(values),
                    value_raw=mean,
                    standard_error=standard_error,
                    value_display=display,
                    units=units,
                    evidence_id=record.evidence_id,
                )
            )
        for true_action, true_name in enumerate(("no_email", "mens_email", "womens_email")):
            for predicted_action, predicted_name in enumerate(
                ("no_email", "mens_email", "womens_email")
            ):
                values = np.asarray(
                    [
                        row.action_confusion_matrix[true_action][predicted_action]
                        for row in scenario_rows
                    ]
                )
                mean = float(np.mean(values))
                standard_error = (
                    0.0
                    if len(values) == 1
                    else float(np.std(values, ddof=1) / np.sqrt(len(values)))
                )
                metric = f"confusion_true_{true_name}_predicted_{predicted_name}"
                display = format(mean, ".6g")
                record = build_evidence_record(
                    track=dataset.manifest.track,
                    evidence_status=dataset.manifest.evidence_status,
                    estimator_backend=dataset.manifest.estimator_backend,
                    execution_profile=dataset.manifest.execution_profile,
                    run_id=run_id,
                    dataset_hash=dataset.manifest.dataset_hash,
                    specification_id=specification_id,
                    result_bundle_id=bundle_id,
                    claim_type=f"semisynthetic:{scenario}:{metric}:replication_mean",
                    value_raw=mean,
                    value_display=display,
                    units="proportion",
                    support_status=SupportStatus.SUPPORTED,
                    warnings=warnings,
                    source_artifact=source_artifact,
                    source_artifact_hash=source_hash,
                )
                records.append(record)
                estimates.append(
                    SemiSyntheticEstimate(
                        scenario=scenario,
                        metric=metric,
                        replication_count=len(values),
                        value_raw=mean,
                        standard_error=standard_error,
                        value_display=display,
                        units="proportion",
                        evidence_id=record.evidence_id,
                    )
                )
    ledger = EvidenceLedger(records)
    bundle = SemiSyntheticEvaluationBundle(
        result_bundle_id=bundle_id,
        run_id=run_id,
        specification_id=specification_id,
        dataset_hash=dataset.manifest.dataset_hash,
        track=dataset.manifest.track,
        execution_profile=dataset.manifest.execution_profile,
        estimator_backend=dataset.manifest.estimator_backend,
        evidence_status=dataset.manifest.evidence_status,
        split_manifest_id=split.split_manifest_id,
        data_label=data_label,
        values=tuple(estimates),
        warnings=warnings,
        assumptions=assumptions,
        source_artifact=source_artifact,
        source_artifact_hash=source_hash,
    )
    validate_semisynthetic_bundle_evidence(bundle, ledger)
    audit.append(
        event_type="four_scenario_benchmark_completed",
        stage="hillstrom.semisynthetic",
        status="completed",
        run_id=run_id,
        details=(("replication_count", str(len(replications_raw))),),
    )

    artifact_paths: list[tuple[str, Path]] = []
    artifact_hashes: list[tuple[str, str]] = []
    if output_dir is not None:
        report_manifest = {
            "track": dataset.manifest.track,
            "execution_profile": dataset.manifest.execution_profile,
            "estimator_backend": dataset.manifest.estimator_backend,
            "evidence_status": dataset.manifest.evidence_status,
            "result_bundle_id": bundle.result_bundle_id,
            "evidence_ids": tuple(record.evidence_id for record in records),
            "report_logic": "pure_render_from_validated_semisynthetic_bundle",
        }
        artifacts: tuple[tuple[str, str, object | bytes], ...] = (
            ("specification", "specification.json", specification),
            ("dataset_manifest", "dataset_manifest.json", dataset.manifest),
            ("split_manifest", "split_manifest.json", split),
            ("backend_manifest", "backend_manifest.json", backend_manifest),
            ("semisynthetic_numerical_core", source_artifact, numerical_core),
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
        dataset_hash=dataset.manifest.dataset_hash,
        backend_manifest_id=backend_manifest_id,
        track=dataset.manifest.track,
        execution_profile=dataset.manifest.execution_profile,
        estimator_backend=dataset.manifest.estimator_backend,
        evidence_status=dataset.manifest.evidence_status,
        seed=seed,
        artifact_hashes=tuple(artifact_hashes),
    )
    if output_dir is not None:
        path = output_dir / "run_manifest.json"
        _write_json(path, run_manifest)
        artifact_paths.append(("run_manifest", path))
    return SemiSyntheticRun(
        bundle=bundle,
        ledger=ledger,
        audit=audit,
        run_manifest=run_manifest,
        replications=replications_raw,
        artifact_paths=tuple(artifact_paths),
    )
