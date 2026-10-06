"""No-LLM Track H vertical slice with an explicit freeze-before-test gate."""

from __future__ import annotations

import importlib.metadata
import os
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

import numpy as np

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
from dcfa.errors import DCFAError, ErrorCode
from dcfa.evidence import EvidenceLedger, build_evidence_record, validate_policy_bundle_evidence
from dcfa.hillstrom_policy.contracts import (
    HILLSTROM_ACTIONS,
    FrozenPolicyArtifact,
    HillstromDataset,
    HillstromPolicySpecification,
    SplitManifest,
)
from dcfa.hillstrom_policy.data import (
    TestOutcomeGate,
    validate_hillstrom_split,
)
from dcfa.hillstrom_policy.estimators import (
    design_propensities,
    direct_scores,
    doubly_robust_scores,
    empirical_propensities,
    ipw_scores,
    paired_policy_contrast,
    policy_influence_scores,
    summarize_scores,
)
from dcfa.hillstrom_policy.policies import (
    fit_frozen_policy,
    predict_frozen_policy,
    uniform_policy,
)
from dcfa.output import require_fresh_output_directory
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.schemas import (
    EvidenceRecord,
    PolicyContrastEstimate,
    PolicyEvaluationBundle,
    PolicyValueEstimate,
    RCTEffectEstimate,
    RunManifest,
    WarningRecord,
)


@dataclass(frozen=True)
class HillstromAnalysisRun:
    bundle: PolicyEvaluationBundle
    ledger: EvidenceLedger
    audit: AuditTrail
    run_manifest: RunManifest
    policy_artifact: FrozenPolicyArtifact
    artifact_paths: tuple[tuple[str, Path], ...]
    test_outcomes_accessed_after_freeze: bool


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


def _validate_contracts(
    dataset: HillstromDataset,
    split: SplitManifest,
    specification: HillstromPolicySpecification,
) -> None:
    validate_hillstrom_split(split, dataset)
    expected = (
        specification.track,
        specification.execution_profile,
        specification.estimator_backend,
        specification.evidence_status,
    )
    if expected[0] is not Track.HILLSTROM_POLICY:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Hillstrom evaluator accepts only the isolated Track H contract.",
            stage="hillstrom.contract",
        )
    if specification.specification_version != "hillstrom_policy_v5":
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Track H accepts only specification_version='hillstrom_policy_v5'.",
            stage="hillstrom.contract",
        )
    if expected[2] is not EstimatorBackend.SKLEARN_POLICY:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "Track H v1 has one explicit deterministic sklearn_policy backend.",
            stage="hillstrom.contract",
        )
    observed = (
        dataset.manifest.track,
        dataset.manifest.execution_profile,
        dataset.manifest.estimator_backend,
        dataset.manifest.evidence_status,
    )
    if observed != expected:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "Dataset and policy execution/evidence markers differ.",
            stage="hillstrom.contract",
        )
    if specification.execution_profile is ExecutionProfile.LOCAL_DEVELOPMENT:
        if specification.evidence_status is not EvidenceStatus.DEVELOPMENT_ONLY:
            raise DCFAError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Local Track H execution must remain development_only.",
                stage="hillstrom.contract",
            )
    elif specification.execution_profile is ExecutionProfile.LOCKED_EVALUATION:
        if specification.evidence_status is not EvidenceStatus.ELIGIBLE_FOR_RELEASE:
            raise DCFAError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Locked Track H execution must use release-eligible evidence status.",
                stage="hillstrom.contract",
            )
    else:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "Track H accepts only local_development or locked_evaluation profiles.",
            stage="hillstrom.contract",
        )
    if dataset.manifest.dataset_hash != specification.dataset_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Dataset hash differs from the immutable policy specification.",
            stage="hillstrom.contract",
        )
    if split.split_manifest_id != specification.split_manifest_id:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Split differs from the immutable policy specification.",
            stage="hillstrom.contract",
        )
    if split.dataset_hash != dataset.manifest.dataset_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Split manifest does not belong to the immutable dataset.",
            stage="hillstrom.contract",
        )
    if specification.objective.outcome != "spend":
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Track H policy primary outcome must be two-week spend.",
            stage="hillstrom.contract",
        )
    if specification.objective.horizon != "two_weeks":
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Track H v5 fixes the policy horizon to two_weeks.",
            stage="hillstrom.contract",
        )
    if (
        not isinstance(specification.objective.margin, Real)
        or isinstance(specification.objective.margin, bool)
        or not np.isfinite(specification.objective.margin)
        or specification.objective.margin != 1.0
    ):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Track H v1 fixes margin=1.0; other margins are not silently ignored.",
            stage="hillstrom.contract",
        )
    if any(
        not isinstance(value, Real) or isinstance(value, bool)
        for value in specification.objective.action_costs
    ):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Action costs must be numeric scalar values.",
            stage="hillstrom.contract",
        )
    costs = np.asarray(specification.objective.action_costs, dtype=float)
    if costs.shape != (len(HILLSTROM_ACTIONS),) or not np.all(np.isfinite(costs)):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Action costs must be a finite value for each frozen categorical action.",
            stage="hillstrom.contract",
        )
    if specification.fallback_action not in HILLSTROM_ACTIONS:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Fallback action is outside the frozen categorical action set.",
            stage="hillstrom.contract",
        )
    if any(
        not isinstance(value, Real) or isinstance(value, bool)
        for value in specification.uncertainty_threshold_candidates
    ):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Uncertainty-threshold candidates must be numeric scalar values.",
            stage="hillstrom.contract",
        )
    thresholds = np.asarray(specification.uncertainty_threshold_candidates, dtype=float)
    if (
        thresholds.size == 0
        or not np.all(np.isfinite(thresholds))
        or np.any(thresholds < 0.0)
        or tuple(sorted(set(thresholds))) != tuple(thresholds)
    ):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Uncertainty-threshold candidates must be finite, nonnegative, and non-empty.",
            stage="hillstrom.contract",
        )
    if specification.capacity_fraction is not None and (
        not isinstance(specification.capacity_fraction, Real)
        or isinstance(specification.capacity_fraction, bool)
        or not np.isfinite(specification.capacity_fraction)
        or not 0.0 <= specification.capacity_fraction <= 1.0
    ):
        raise DCFAError(
            ErrorCode.CONSTRAINT_VIOLATION,
            "Email capacity fraction must lie in [0, 1].",
            stage="hillstrom.contract",
        )
    if specification.propensity_source != "design_equal_thirds":
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "The Track H primary propensity is frozen to design_equal_thirds.",
            stage="hillstrom.contract",
        )
    if not isinstance(specification.seed, int) or isinstance(specification.seed, bool):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Track H seed must be an integer.",
            stage="hillstrom.contract",
        )


def _baseline_balance(dataset: HillstromDataset) -> tuple[tuple[str, float], ...]:
    """Maximum pairwise standardized mean difference by baseline feature."""
    actions = np.asarray(dataset.actions, dtype=int)

    def max_pairwise(values: np.ndarray) -> float:
        result = 0.0
        overall_scale = float(np.std(values))
        for left in range(len(HILLSTROM_ACTIONS)):
            for right in range(left + 1, len(HILLSTROM_ACTIONS)):
                left_values = values[actions == left]
                right_values = values[actions == right]
                difference = abs(float(np.mean(left_values) - np.mean(right_values)))
                pooled = float(
                    np.sqrt((np.var(left_values, ddof=1) + np.var(right_values, ddof=1)) / 2.0)
                )
                denominator = pooled if pooled > 1e-12 else max(overall_scale, 1e-12)
                result = max(result, difference / denominator)
        return result

    summaries: list[tuple[str, float]] = []
    for name, raw_values in dataset.feature_columns:
        try:
            numeric = np.asarray(raw_values, dtype=float)
        except ValueError:
            levels = sorted({str(value) for value in raw_values})
            value = max(
                max_pairwise((np.asarray(raw_values, dtype=str) == level).astype(float))
                for level in levels
            )
        else:
            value = max_pairwise(numeric)
        summaries.append((name, float(value)))
    return tuple(summaries)


def _report(bundle: PolicyEvaluationBundle) -> str:
    lines = [
        "# Track H held-out policy evaluation",
        "",
        f"- track: `{bundle.track.value}`",
        f"- execution_profile: `{bundle.execution_profile.value}`",
        f"- estimator_backend: `{bundle.estimator_backend.value}`",
        f"- evidence_status: `{bundle.evidence_status.value}`",
        f"- frozen policy: `{bundle.policy_id}`",
        "",
        (
            "Values below are held-out average two-week spend per customer under the stated "
            "action-cost specification. They are not individual optimal-action labels, "
            "oracle regret, or validation of TabCF."
        ),
        "",
        "## Policy values",
        "",
        "| Policy | Method | Estimate | 95% influence-score interval | Evidence |",
        "|---|---:|---:|---:|---|",
    ]
    for estimate in bundle.values:
        lines.append(
            f"| {estimate.policy_name} | {estimate.method} | {estimate.value_display} | "
            f"[{estimate.interval_lower:.6g}, {estimate.interval_upper:.6g}] | "
            f"`{estimate.evidence_id}` |"
        )
    lines.extend(
        [
            "",
            "## Paired policy contrasts",
            "",
            "| Policy minus baseline | Method | Estimate | 95% interval | Evidence |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for estimate in bundle.contrasts:
        lines.append(
            f"| {estimate.policy_name} minus {estimate.baseline_policy_name} | "
            f"{estimate.method} | {estimate.value_display} | "
            f"[{estimate.interval_lower:.6g}, {estimate.interval_upper:.6g}] | "
            f"`{estimate.evidence_id}` |"
        )
    lines.extend(
        [
            "",
            "## Held-out randomized-arm effects",
            "",
            "| Outcome | Action minus baseline | Estimate | 95% interval | Evidence |",
            "|---|---|---:|---:|---|",
        ]
    )
    for estimate in bundle.experimental_effects:
        lines.append(
            f"| {estimate.outcome} | {estimate.action} minus {estimate.baseline_action} | "
            f"{estimate.value_display} | "
            f"[{estimate.interval_lower:.6g}, {estimate.interval_upper:.6g}] | "
            f"`{estimate.evidence_id}` |"
        )
    lines.extend(
        [
            "",
            "## Frozen operational specification and allocation",
            "",
            f"- test rows: {bundle.test_row_count}",
            f"- email capacity fraction: {bundle.capacity_fraction}",
            f"- expected email volume: {sum(item[1] for item in bundle.action_allocations[1:])}",
            "",
            "| Action | Cost | Test allocation count | Allocation proportion |",
            "|---|---:|---:|---:|",
        ]
    )
    for action_index, (action, count, proportion) in enumerate(bundle.action_allocations):
        lines.append(
            f"| {action} | {bundle.action_costs[action_index]:.6g} | {count} | {proportion:.6g} |"
        )
    lines.extend(
        [
            "",
            "## H0 data audit",
            "",
            f"- missingness status: `{bundle.missingness_status}`",
            "- Baseline balance values are empirical randomization diagnostics; they do not "
            "prove exchangeability or identify individual optimal actions.",
            "",
            "| Baseline feature | Maximum pairwise absolute SMD |",
            "|---|---:|",
        ]
    )
    lines.extend(f"| {name} | {value:.6g} |" for name, value in bundle.baseline_balance)
    lines.extend(["", "## Assumptions", ""])
    lines.extend(f"- {assumption}" for assumption in bundle.assumptions)
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- `{warning.code}`: {warning.message}" for warning in bundle.warnings)
    return "\n".join(lines) + "\n"


class HillstromPolicyEngine:
    """Fit/freeze first, then unlock and evaluate the untouched test outcomes once."""

    def analyze(
        self,
        dataset: HillstromDataset,
        split: SplitManifest,
        specification: HillstromPolicySpecification,
        *,
        output_dir: Path | None = None,
    ) -> HillstromAnalysisRun:
        _validate_contracts(dataset, split, specification)
        require_fresh_output_directory(output_dir)
        audit = AuditTrail(
            specification_id=specification.specification_id,
            track=specification.track,
            execution_profile=specification.execution_profile,
            estimator_backend=specification.estimator_backend,
            evidence_status=specification.evidence_status,
        )
        audit.append(event_type="split_validated", stage="hillstrom.split", status="completed")
        gate = TestOutcomeGate(dataset, split)
        baseline_balance = _baseline_balance(dataset)
        data_audit = {
            "track": specification.track,
            "execution_profile": specification.execution_profile,
            "estimator_backend": specification.estimator_backend,
            "evidence_status": specification.evidence_status,
            "dataset_hash": dataset.manifest.dataset_hash,
            "split_manifest_id": split.split_manifest_id,
            "arm_counts": dataset.manifest.arm_counts,
            "missingness_status": "validated_zero_missing_or_nonfinite_values",
            "baseline_balance_max_pairwise_absolute_smd": baseline_balance,
        }
        audit.append(
            event_type="data_audit_completed",
            stage="hillstrom.data_audit",
            status="baseline_features_and_randomized_assignment_only",
            details=(
                ("missingness_status", "validated_zero_missing_or_nonfinite_values"),
                (
                    "maximum_absolute_smd",
                    format(max(value for _, value in baseline_balance), ".6g"),
                ),
            ),
        )

        fit = fit_frozen_policy(dataset, split, specification)
        policy = fit.artifact
        if gate.test_outcomes_accessed:
            raise AssertionError("Test outcome gate opened before policy freeze.")
        if output_dir is not None:
            _write_json(output_dir / "policy_artifact.json", policy)
        policy_artifact_hash = (
            file_sha256(output_dir / "policy_artifact.json")
            if output_dir is not None
            else sha256_digest(policy)
        )
        audit.append(
            event_type="policy_frozen",
            stage="hillstrom.policy.freeze",
            status="completed_before_test_outcome_access",
            details=(("policy_id", policy.policy_id), ("artifact_hash", policy_artifact_hash)),
        )
        backend_manifest = {
            "track": specification.track,
            "execution_profile": specification.execution_profile,
            "estimator_backend": specification.estimator_backend,
            "evidence_status": specification.evidence_status,
            "protocol_version": "hillstrom_policy_v5",
            "tool_version": __version__,
            "dcfa_source_tree_hash": dcfa_source_tree_hash(),
            "package_versions": (
                ("numpy", importlib.metadata.version("numpy")),
                ("scikit-learn", importlib.metadata.version("scikit-learn")),
            ),
            "model": "per_action_ridge_closed_form",
            "propensity": specification.propensity_source,
            "policy_id": policy.policy_id,
            "policy_artifact_hash": policy_artifact_hash,
        }
        backend_manifest_id = content_id("backend", backend_manifest)

        test_features = gate.test_features(policy.preprocessing)
        personalized, outcome_predictions = predict_frozen_policy(policy, test_features)
        test_actions, test_outcomes = gate.unlock(policy)
        test_conversion = gate.unlock_named_outcome(policy, "conversion")
        test_visit = gate.unlock_named_outcome(policy, "visit")
        audit.append(
            event_type="test_outcomes_unlocked",
            stage="hillstrom.test_gate",
            status="completed_after_policy_freeze",
            details=(("policy_id", policy.policy_id),),
        )

        primary_propensities = design_propensities(len(test_actions))
        sensitivity_propensities = empirical_propensities(test_actions)
        score_matrices = {
            "dr": doubly_robust_scores(
                test_outcomes, test_actions, outcome_predictions, primary_propensities
            ),
            "ipw": ipw_scores(
                test_outcomes, test_actions, outcome_predictions, primary_propensities
            ),
            "direct": direct_scores(
                test_outcomes, test_actions, outcome_predictions, primary_propensities
            ),
        }
        empirical_dr = doubly_robust_scores(
            test_outcomes,
            test_actions,
            outcome_predictions,
            sensitivity_propensities,
        )
        named_policies = {
            HILLSTROM_ACTIONS[action]: uniform_policy(len(test_actions), action)
            for action in range(len(HILLSTROM_ACTIONS))
        }
        named_policies["best_uniform_validation_selected"] = uniform_policy(
            len(test_actions), fit.best_uniform_action
        )
        named_policies[policy.policy_name] = personalized
        costs = specification.objective.action_costs

        core_values: list[dict[str, object]] = []
        for policy_name, probabilities in named_policies.items():
            for method, score_matrix in score_matrices.items():
                summary = summarize_scores(
                    policy_influence_scores(score_matrix, probabilities, costs)
                )
                core_values.append(
                    {
                        "policy_name": policy_name,
                        "method": method,
                        **summary.__dict__,
                    }
                )
        empirical_propensity_summary = summarize_scores(
            policy_influence_scores(empirical_dr, personalized, costs)
        )
        core_values.append(
            {
                "policy_name": policy.policy_name,
                "method": "dr_empirical_propensity_sensitivity",
                **empirical_propensity_summary.__dict__,
            }
        )
        core_contrasts: list[dict[str, object]] = []
        for baseline_name in ("no_email", "best_uniform_validation_selected"):
            for method, score_matrix in score_matrices.items():
                summary = paired_policy_contrast(
                    score_matrix,
                    personalized,
                    named_policies[baseline_name],
                    costs,
                )
                core_contrasts.append(
                    {
                        "policy_name": policy.policy_name,
                        "baseline_policy_name": baseline_name,
                        "method": method,
                        **summary.__dict__,
                    }
                )

        core_effects: list[dict[str, object]] = []
        for outcome_name, outcome_values in (
            ("spend", test_outcomes),
            ("conversion", test_conversion),
            ("visit", test_visit),
        ):
            for action, baseline_action in ((1, 0), (2, 0), (1, 2)):
                treated = outcome_values[test_actions == action]
                baseline = outcome_values[test_actions == baseline_action]
                value = float(np.mean(treated) - np.mean(baseline))
                standard_error = float(
                    np.sqrt(
                        np.var(treated, ddof=1) / len(treated)
                        + np.var(baseline, ddof=1) / len(baseline)
                    )
                )
                core_effects.append(
                    {
                        "outcome": outcome_name,
                        "action": HILLSTROM_ACTIONS[action],
                        "baseline_action": HILLSTROM_ACTIONS[baseline_action],
                        "value": value,
                        "standard_error": standard_error,
                        "interval_lower": value - 1.96 * standard_error,
                        "interval_upper": value + 1.96 * standard_error,
                    }
                )

        warnings = (
            WarningRecord(
                code="DEVELOPMENT_FIXTURE_NOT_REAL_HILLSTROM"
                if dataset.manifest.source_kind != "real_randomized_experiment"
                else "REAL_RCT_HAS_NO_INDIVIDUAL_ORACLE",
                message=(
                    "This generated RCT validates mechanics only and is not real "
                    "Hillstrom evidence."
                    if dataset.manifest.source_kind != "real_randomized_experiment"
                    else "The real RCT identifies held-out average policy value, not individual "
                    "optimal-action correctness or oracle regret."
                ),
                severity=WarningSeverity.WARNING,
                source="hillstrom.evidence_boundary",
            ),
            WarningRecord(
                code="SPEND_NOT_PROFIT",
                message="The outcome is two-week spend; no profit interpretation is made.",
                severity=WarningSeverity.INFO,
                source="hillstrom.objective",
            ),
        )
        run_id = content_id(
            "hillstrom_run",
            {
                "specification_id": specification.specification_id,
                "dataset_hash": specification.dataset_hash,
                "policy_id": policy.policy_id,
                "backend_manifest_id": backend_manifest_id,
            },
        )
        action_allocations = tuple(
            (
                HILLSTROM_ACTIONS[action],
                int(np.sum(np.argmax(personalized, axis=1) == action)),
                float(np.mean(np.argmax(personalized, axis=1) == action)),
            )
            for action in range(len(HILLSTROM_ACTIONS))
        )
        numerical_core = {
            "track": specification.track,
            "execution_profile": specification.execution_profile,
            "estimator_backend": specification.estimator_backend,
            "evidence_status": specification.evidence_status,
            "run_id": run_id,
            "specification_id": specification.specification_id,
            "dataset_hash": specification.dataset_hash,
            "policy_id": policy.policy_id,
            "backend_manifest_id": backend_manifest_id,
            "split_manifest_id": split.split_manifest_id,
            "outcome": specification.objective.outcome,
            "horizon": specification.objective.horizon,
            "test_row_count": len(test_actions),
            "action_costs": costs,
            "capacity_fraction": specification.capacity_fraction,
            "policy_values": tuple(core_values),
            "policy_contrasts": tuple(core_contrasts),
            "experimental_effects": tuple(core_effects),
            "action_allocations": action_allocations,
            "dataset_arm_counts": dataset.manifest.arm_counts,
            "missingness_status": data_audit["missingness_status"],
            "baseline_balance": baseline_balance,
            "warnings": warnings,
            "assumptions": (
                "Randomized assignment probabilities are exactly one third in the primary score.",
                "Empirical arm frequencies appear only in the explicitly labeled DR sensitivity.",
                "The policy, objective, costs, capacity, and threshold were frozen "
                "before test outcomes.",
                "DR, IPW, and direct estimates use the same untouched test customers.",
            ),
        }
        source_artifact = "policy_numerical_core.json"
        if output_dir is not None:
            _write_json(output_dir / source_artifact, numerical_core)
            source_hash = file_sha256(output_dir / source_artifact)
        else:
            source_hash = sha256_digest(numerical_core)
        bundle_id = content_id("policy_bundle", numerical_core)

        records: list[EvidenceRecord] = []
        values: list[PolicyValueEstimate] = []
        for item in core_values:
            value = float(item["value"])
            display = format(value, ".6g")
            claim_type = f"policy_value:{item['policy_name']}:{item['method']}"
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
                units="two_week_spend_per_customer",
                support_status=SupportStatus.SUPPORTED,
                warnings=warnings,
                source_artifact=source_artifact,
                source_artifact_hash=source_hash,
            )
            records.append(record)
            values.append(
                PolicyValueEstimate(
                    policy_name=str(item["policy_name"]),
                    method=str(item["method"]),
                    value_raw=value,
                    standard_error=float(item["standard_error"]),
                    interval_lower=float(item["interval_lower"]),
                    interval_upper=float(item["interval_upper"]),
                    value_display=display,
                    units="two_week_spend_per_customer",
                    evidence_id=record.evidence_id,
                )
            )
        contrasts: list[PolicyContrastEstimate] = []
        for item in core_contrasts:
            value = float(item["value"])
            display = format(value, ".6g")
            claim_type = (
                f"paired_policy_contrast:{item['policy_name']}:minus:"
                f"{item['baseline_policy_name']}:{item['method']}"
            )
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
                units="two_week_spend_per_customer_difference",
                support_status=SupportStatus.SUPPORTED,
                warnings=warnings,
                source_artifact=source_artifact,
                source_artifact_hash=source_hash,
            )
            records.append(record)
            contrasts.append(
                PolicyContrastEstimate(
                    policy_name=str(item["policy_name"]),
                    baseline_policy_name=str(item["baseline_policy_name"]),
                    method=str(item["method"]),
                    value_raw=value,
                    standard_error=float(item["standard_error"]),
                    interval_lower=float(item["interval_lower"]),
                    interval_upper=float(item["interval_upper"]),
                    value_display=display,
                    units="two_week_spend_per_customer_difference",
                    evidence_id=record.evidence_id,
                )
            )
        experimental_effects: list[RCTEffectEstimate] = []
        for item in core_effects:
            value = float(item["value"])
            display = format(value, ".6g")
            units = (
                "two_week_spend_per_customer_difference"
                if item["outcome"] == "spend"
                else "probability_difference"
            )
            record = build_evidence_record(
                track=specification.track,
                evidence_status=specification.evidence_status,
                estimator_backend=specification.estimator_backend,
                execution_profile=specification.execution_profile,
                run_id=run_id,
                dataset_hash=specification.dataset_hash,
                specification_id=specification.specification_id,
                result_bundle_id=bundle_id,
                claim_type=(
                    f"randomized_arm_effect:{item['outcome']}:{item['action']}:minus:"
                    f"{item['baseline_action']}"
                ),
                value_raw=value,
                value_display=display,
                units=units,
                support_status=SupportStatus.SUPPORTED,
                warnings=warnings,
                source_artifact=source_artifact,
                source_artifact_hash=source_hash,
            )
            records.append(record)
            experimental_effects.append(
                RCTEffectEstimate(
                    outcome=str(item["outcome"]),
                    action=str(item["action"]),
                    baseline_action=str(item["baseline_action"]),
                    value_raw=value,
                    standard_error=float(item["standard_error"]),
                    interval_lower=float(item["interval_lower"]),
                    interval_upper=float(item["interval_upper"]),
                    value_display=display,
                    units=units,
                    evidence_id=record.evidence_id,
                )
            )
        ledger = EvidenceLedger(records)
        bundle = PolicyEvaluationBundle(
            result_bundle_id=bundle_id,
            run_id=run_id,
            specification_id=specification.specification_id,
            dataset_hash=specification.dataset_hash,
            track=specification.track,
            execution_profile=specification.execution_profile,
            estimator_backend=specification.estimator_backend,
            evidence_status=specification.evidence_status,
            policy_id=policy.policy_id,
            split_manifest_id=split.split_manifest_id,
            outcome=specification.objective.outcome,
            horizon=specification.objective.horizon,
            test_row_count=int(numerical_core["test_row_count"]),
            action_costs=costs,
            capacity_fraction=specification.capacity_fraction,
            values=tuple(values),
            contrasts=tuple(contrasts),
            experimental_effects=tuple(experimental_effects),
            action_allocations=tuple(numerical_core["action_allocations"]),
            dataset_arm_counts=dataset.manifest.arm_counts,
            missingness_status=str(numerical_core["missingness_status"]),
            baseline_balance=baseline_balance,
            warnings=warnings,
            assumptions=tuple(numerical_core["assumptions"]),
            source_artifact=source_artifact,
            source_artifact_hash=source_hash,
        )
        validate_policy_bundle_evidence(bundle, ledger)
        audit.append(
            event_type="held_out_evaluation_completed",
            stage="hillstrom.policy_value",
            status="completed",
            run_id=run_id,
            details=(("evidence_count", str(len(records))),),
        )

        artifact_paths: list[tuple[str, Path]] = []
        artifact_hashes: list[tuple[str, str]] = []
        if output_dir is not None:
            report = _report(bundle)
            report_manifest = {
                "track": specification.track,
                "execution_profile": specification.execution_profile,
                "estimator_backend": specification.estimator_backend,
                "evidence_status": specification.evidence_status,
                "result_bundle_id": bundle.result_bundle_id,
                "evidence_ids": tuple(record.evidence_id for record in records),
                "report_logic": "pure_render_from_validated_policy_bundle",
            }
            artifacts: tuple[tuple[str, str, object | bytes], ...] = (
                ("specification", "specification.json", specification),
                ("dataset_manifest", "dataset_manifest.json", dataset.manifest),
                ("split_manifest", "split_manifest.json", split),
                ("data_audit", "data_audit.json", data_audit),
                ("backend_manifest", "backend_manifest.json", backend_manifest),
                ("policy_artifact", "policy_artifact.json", policy),
                ("policy_numerical_core", source_artifact, numerical_core),
                ("result_bundle", "result_bundle.json", bundle),
                ("evidence", "evidence_records.jsonl", tuple(records)),
                ("audit", "audit.jsonl", audit.events()),
                ("report", "report.md", report.encode("utf-8")),
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
            specification_id=specification.specification_id,
            dataset_hash=specification.dataset_hash,
            backend_manifest_id=backend_manifest_id,
            track=specification.track,
            execution_profile=specification.execution_profile,
            estimator_backend=specification.estimator_backend,
            evidence_status=specification.evidence_status,
            seed=specification.seed,
            artifact_hashes=tuple(artifact_hashes),
        )
        if output_dir is not None:
            path = output_dir / "run_manifest.json"
            _write_json(path, run_manifest)
            artifact_paths.append(("run_manifest", path))
        return HillstromAnalysisRun(
            bundle=bundle,
            ledger=ledger,
            audit=audit,
            run_manifest=run_manifest,
            policy_artifact=policy,
            artifact_paths=tuple(artifact_paths),
            test_outcomes_accessed_after_freeze=gate.test_outcomes_accessed,
        )
