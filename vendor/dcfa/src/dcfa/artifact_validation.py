"""Independent verification of a saved DCFA result directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from dcfa.canonical import content_id, file_sha256, to_primitive
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import DCFAError, ErrorCode
from dcfa.provenance import dcfa_source_tree_hash

REQUIRED_MARKERS = ("track", "execution_profile", "estimator_backend", "evidence_status")


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant is forbidden: {value}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            f"Could not load required JSON artifact {path.name}.",
            stage="artifact.validation",
        ) from exc
    if not isinstance(value, dict):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            f"Artifact {path.name} must contain a JSON object.",
            stage="artifact.validation",
        )
    return value


def _load_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line, parse_constant=_reject_nonfinite_json)
            if not isinstance(value, dict):
                raise TypeError("JSONL record is not an object")
            records.append(value)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            f"Could not load required JSONL artifact {path.name}.",
            stage="artifact.validation",
        ) from exc
    return tuple(records)


def _assert_markers(
    value: dict[str, Any],
    expected: dict[str, str],
    *,
    artifact_name: str,
) -> None:
    mismatches = {
        marker: {"expected": expected[marker], "observed": value.get(marker)}
        for marker in REQUIRED_MARKERS
        if value.get(marker) != expected[marker]
    }
    if mismatches:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            f"Execution/evidence markers mismatch in {artifact_name}.",
            stage="artifact.validation",
            context={"mismatches": mismatches},
        )


def _assert_equal_identity(
    *,
    name: str,
    expected: str,
    observed_values: tuple[tuple[str, Any], ...],
) -> None:
    mismatches = {
        location: {"expected": expected, "observed": observed}
        for location, observed in observed_values
        if observed != expected
    }
    if mismatches:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            f"Content-addressed {name} does not match its saved payload.",
            stage="artifact.validation",
            context={"mismatches": mismatches},
        )


def _validate_marker_contract(expected: dict[str, str], variant: str) -> None:
    profile_status = (expected["execution_profile"], expected["evidence_status"])
    allowed_profile_status = {
        (ExecutionProfile.LOCAL_DEVELOPMENT.value, EvidenceStatus.DEVELOPMENT_ONLY.value),
        (ExecutionProfile.LOCKED_EVALUATION.value, EvidenceStatus.ELIGIBLE_FOR_RELEASE.value),
    }
    failures: list[str] = []
    if variant in {"hillstrom_policy", "semisynthetic"}:
        if expected["track"] != Track.HILLSTROM_POLICY.value:
            failures.append("wrong_track")
        if expected["estimator_backend"] != EstimatorBackend.SKLEARN_POLICY.value:
            failures.append("wrong_backend")
        if profile_status not in allowed_profile_status:
            failures.append("invalid_profile_status")
    elif variant == "track_t_development":
        required = (
            Track.TABCF_IV.value,
            ExecutionProfile.LOCAL_DEVELOPMENT.value,
            EstimatorBackend.SKLEARN_QUANTILE_FALLBACK.value,
            EvidenceStatus.DEVELOPMENT_ONLY.value,
        )
        if tuple(expected[marker] for marker in REQUIRED_MARKERS) != required:
            failures.append("invalid_development_track_t_markers")
    else:
        if expected["track"] != Track.TABCF_IV.value:
            failures.append("wrong_track")
        backend = expected["estimator_backend"]
        if backend == EstimatorBackend.SKLEARN_QUANTILE_FALLBACK.value:
            required_pair = (
                ExecutionProfile.LOCAL_DEVELOPMENT.value,
                EvidenceStatus.DEVELOPMENT_ONLY.value,
            )
            if profile_status != required_pair:
                failures.append("fallback_promoted_outside_development")
        elif backend == EstimatorBackend.TABPFN.value:
            if profile_status not in allowed_profile_status:
                failures.append("invalid_tabpfn_profile_status")
        else:
            failures.append("unsupported_tabcf_backend")
    if failures:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Saved execution/evidence markers violate the track contract.",
            stage="artifact.validation",
            context={"failures": failures},
        )


def _assert_projection(*, name: str, expected: Any, observed: Any) -> None:
    if observed != expected:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            f"Saved {name} is not the deterministic projection of its numerical core.",
            stage="artifact.validation",
        )


def _mean_and_standard_error(values: list[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    mean = float(np.mean(array))
    standard_error = 0.0 if len(array) == 1 else float(np.std(array, ddof=1) / np.sqrt(len(array)))
    return mean, standard_error


def _validate_tabcf_projection(
    specification: dict[str, Any],
    numerical_core: dict[str, Any],
    bundle: dict[str, Any],
) -> None:
    direct_fields = (
        "x_grid",
        "y_grid",
        "interventional_cdf",
        "interventional_mean",
        "quantile_levels",
        "interventional_quantiles",
        "risk_thresholds",
        "interventional_risks",
        "diagnostics",
        "support",
    )
    for field in direct_fields:
        _assert_projection(
            name=f"TabCF bundle field {field}",
            expected=numerical_core.get(field),
            observed=bundle.get(field),
        )
    if specification.get("distribution") is not None:
        # Validate saved artifacts against the saved numerical core. Recomputing
        # exp/finite differences on another platform can change the last bits.
        projection = numerical_core["distribution"]
        _assert_projection(
            name="saved original-unit distribution",
            expected=projection,
            observed=bundle.get("distribution"),
        )
        queries = bundle.get("queries", [])
        _assert_projection(
            name="distribution query count",
            expected=len(projection["metrics"]),
            observed=len(queries),
        )
        status = (
            "weak_support"
            if any(s["status"] == "weak_support" for s in numerical_core["support"])
            else "supported"
        )
        for metric, query in zip(projection["metrics"], queries, strict=True):
            expected = {
                "query_id": metric["key"],
                "claim_type": "distribution:" + metric["key"],
                "value_raw": metric["value"],
                "value_display": format(metric["value"], ".6g"),
                "units": metric["units"],
                "support_status": status,
                "warnings": numerical_core["warnings"],
            }
            _assert_projection(
                name=metric["key"], expected=expected, observed={k: query.get(k) for k in expected}
            )
        return
    queries = bundle.get("queries")
    query_specs = specification.get("queries")
    if (
        not isinstance(queries, list)
        or not isinstance(query_specs, list)
        or len(queries) != len(query_specs)
    ):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "TabCF query cardinality does not match the immutable specification.",
            stage="artifact.validation",
        )
    x_grid = list(numerical_core["x_grid"])
    levels = list(numerical_core["quantile_levels"])
    thresholds = list(numerical_core["risk_thresholds"])
    support = {item["x"]: item["status"] for item in numerical_core["support"]}
    claim_types = {
        "mean": "interventional_mean",
        "quantile": "interventional_quantile",
        "risk": "threshold_risk",
        "mean_contrast": "mean_contrast_x_minus_comparison_x",
        "quantile_contrast": "quantile_contrast_x_minus_comparison_x",
        "risk_contrast": "risk_contrast_x_minus_comparison_x",
    }
    for query_spec, query in zip(query_specs, queries, strict=True):
        kind = query_spec["kind"]
        x_index = x_grid.index(query_spec["x"])
        comparison_x = query_spec.get("comparison_x")
        if kind in {"mean", "mean_contrast"}:
            values = numerical_core["interventional_mean"]
        elif kind in {"quantile", "quantile_contrast"}:
            level_index = levels.index(query_spec["level"])
            values = [row[level_index] for row in numerical_core["interventional_quantiles"]]
        else:
            threshold_index = thresholds.index(query_spec["threshold"])
            values = [row[threshold_index] for row in numerical_core["interventional_risks"]]
        value = float(values[x_index])
        statuses = [support[query_spec["x"]]]
        if kind.endswith("_contrast"):
            comparison_index = x_grid.index(comparison_x)
            value -= float(values[comparison_index])
            statuses.append(support[comparison_x])
        support_status = (
            "unsupported"
            if "unsupported" in statuses
            else "weak_support"
            if "weak_support" in statuses
            else "supported"
        )
        expected_query = {
            "query_id": query_spec["query_id"],
            "claim_type": claim_types[kind],
            "value_raw": value,
            "value_display": format(value, ".6g"),
            "units": query_spec["units"],
            "support_status": support_status,
            "warnings": numerical_core["warnings"],
        }
        observed_query = {key: query.get(key) for key in expected_query}
        _assert_projection(
            name=f"TabCF query {query_spec['query_id']}",
            expected=expected_query,
            observed=observed_query,
        )


def _validate_policy_projection(
    numerical_core: dict[str, Any],
    bundle: dict[str, Any],
) -> None:
    field_pairs = {
        "policy_id": "policy_id",
        "split_manifest_id": "split_manifest_id",
        "outcome": "outcome",
        "horizon": "horizon",
        "test_row_count": "test_row_count",
        "action_costs": "action_costs",
        "capacity_fraction": "capacity_fraction",
        "action_allocations": "action_allocations",
        "dataset_arm_counts": "dataset_arm_counts",
        "missingness_status": "missingness_status",
        "baseline_balance": "baseline_balance",
    }
    for bundle_field, core_field in field_pairs.items():
        _assert_projection(
            name=f"policy bundle field {bundle_field}",
            expected=numerical_core.get(core_field),
            observed=bundle.get(bundle_field),
        )
    estimate_groups = (
        (
            "values",
            "policy_values",
            ("policy_name", "method"),
            "two_week_spend_per_customer",
        ),
        (
            "contrasts",
            "policy_contrasts",
            ("policy_name", "baseline_policy_name", "method"),
            "two_week_spend_per_customer_difference",
        ),
        (
            "experimental_effects",
            "experimental_effects",
            ("outcome", "action", "baseline_action"),
            None,
        ),
    )
    for bundle_field, core_field, labels, fixed_units in estimate_groups:
        observed_estimates = bundle.get(bundle_field)
        core_estimates = numerical_core.get(core_field)
        if not isinstance(observed_estimates, list) or not isinstance(core_estimates, list):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Policy estimate arrays are malformed.",
                stage="artifact.validation",
            )
        if len(observed_estimates) != len(core_estimates):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Policy estimate cardinality differs from the numerical core.",
                stage="artifact.validation",
            )
        for core_estimate, observed_estimate in zip(
            core_estimates, observed_estimates, strict=True
        ):
            units = fixed_units or (
                "two_week_spend_per_customer_difference"
                if core_estimate["outcome"] == "spend"
                else "probability_difference"
            )
            expected_estimate = {
                **{label: core_estimate[label] for label in labels},
                "value_raw": core_estimate["value"],
                "standard_error": core_estimate["standard_error"],
                "interval_lower": core_estimate["interval_lower"],
                "interval_upper": core_estimate["interval_upper"],
                "value_display": format(float(core_estimate["value"]), ".6g"),
                "units": units,
            }
            _assert_projection(
                name=f"policy estimate {bundle_field}",
                expected=expected_estimate,
                observed={key: observed_estimate.get(key) for key in expected_estimate},
            )


def _validate_aggregate_projection(
    variant: str,
    numerical_core: dict[str, Any],
    bundle: dict[str, Any],
) -> None:
    observed = bundle.get("values")
    if not isinstance(observed, list):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Aggregate bundle values must be a list.",
            stage="artifact.validation",
        )
    expected: list[dict[str, Any]] = []
    if variant == "track_t_development":
        replications = numerical_core.get("replications", [])
        metrics = (
            ("cdf_rmse", "cdf_probability"),
            ("mean_rmse", "Y_units"),
            ("quantile_rmse", "Y_units"),
            ("risk_rmse", "probability"),
            ("empirical_warning_rate", "proportion"),
        )
        for scenario in ("strong_iv", "weak_iv"):
            rows = [row for row in replications if row.get("scenario") == scenario]
            for metric, units in metrics:
                mean, standard_error = _mean_and_standard_error(
                    [float(row[metric]) for row in rows]
                )
                expected.append(
                    {
                        "scenario": scenario,
                        "metric": metric,
                        "seed_count": len(rows),
                        "value_raw": mean,
                        "standard_error": standard_error,
                        "value_display": format(mean, ".6g"),
                        "units": units,
                    }
                )
    else:
        replications = numerical_core.get("replication_results", [])
        metrics = (
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
        actions = ("no_email", "mens_email", "womens_email")
        for scenario in numerical_core.get("scenarios", []):
            rows = [row for row in replications if row.get("scenario") == scenario]
            for metric, units in metrics:
                mean, standard_error = _mean_and_standard_error(
                    [float(row[metric]) for row in rows]
                )
                expected.append(
                    {
                        "scenario": scenario,
                        "metric": metric,
                        "replication_count": len(rows),
                        "value_raw": mean,
                        "standard_error": standard_error,
                        "value_display": format(mean, ".6g"),
                        "units": units,
                    }
                )
            for true_index, true_name in enumerate(actions):
                for predicted_index, predicted_name in enumerate(actions):
                    metric = f"confusion_true_{true_name}_predicted_{predicted_name}"
                    mean, standard_error = _mean_and_standard_error(
                        [
                            float(row["action_confusion_matrix"][true_index][predicted_index])
                            for row in rows
                        ]
                    )
                    expected.append(
                        {
                            "scenario": scenario,
                            "metric": metric,
                            "replication_count": len(rows),
                            "value_raw": mean,
                            "standard_error": standard_error,
                            "value_display": format(mean, ".6g"),
                            "units": "proportion",
                        }
                    )
    if len(observed) != len(expected):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Aggregate estimate cardinality differs from the numerical core.",
            stage="artifact.validation",
        )
    for expected_estimate, observed_estimate in zip(expected, observed, strict=True):
        _assert_projection(
            name=f"{variant} aggregate estimate",
            expected=expected_estimate,
            observed={key: observed_estimate.get(key) for key in expected_estimate},
        )


def verify_run_directory(directory: Path) -> dict[str, Any]:
    """Verify hashes, markers, evidence resolution, and report provenance without fitting."""
    root = Path(directory)
    run_manifest = _load_json(root / "run_manifest.json")
    expected = {marker: str(run_manifest.get(marker)) for marker in REQUIRED_MARKERS}
    _assert_markers(run_manifest, expected, artifact_name="run_manifest.json")

    artifact_hashes = run_manifest.get("artifact_hashes")
    if not isinstance(artifact_hashes, list):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Run manifest artifact_hashes must be a list.",
            stage="artifact.validation",
        )
    verified_hashes: list[str] = []
    for item in artifact_hashes:
        if not isinstance(item, list) or len(item) != 2:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Malformed artifact hash entry.",
                stage="artifact.validation",
            )
        artifact_name, expected_hash = str(item[0]), str(item[1])
        artifact_path = root / {
            "numerical_core": "numerical_core.json",
            "specification": "specification.json",
            "dataset_manifest": "dataset_manifest.json",
            "backend_manifest": "backend_manifest.json",
            "evidence": "evidence_records.jsonl",
            "result_bundle": "result_bundle.json",
            "audit": "audit.jsonl",
            "report": "report.md",
            "plot": "interventional_summary.png",
            "report_manifest": "report_manifest.json",
            "split_manifest": "split_manifest.json",
            "policy_artifact": "policy_artifact.json",
            "data_audit": "data_audit.json",
            "policy_numerical_core": "policy_numerical_core.json",
            "semisynthetic_numerical_core": "semisynthetic_numerical_core.json",
        }.get(artifact_name, artifact_name)
        if not artifact_path.is_file() or file_sha256(artifact_path) != expected_hash:
            raise DCFAError(
                ErrorCode.HASH_MISMATCH,
                f"Artifact hash mismatch for {artifact_name}.",
                stage="artifact.validation",
                context={"artifact": artifact_name},
            )
        verified_hashes.append(artifact_name)

    artifact_keys = {
        str(item[0]) for item in artifact_hashes if isinstance(item, list) and len(item) == 2
    }
    if "semisynthetic_numerical_core" in artifact_keys:
        marker_files = (
            "specification.json",
            "dataset_manifest.json",
            "backend_manifest.json",
            "semisynthetic_numerical_core.json",
            "result_bundle.json",
            "report_manifest.json",
        )
    elif expected["track"] == "hillstrom_policy":
        marker_files = (
            "specification.json",
            "dataset_manifest.json",
            "backend_manifest.json",
            "data_audit.json",
            "policy_artifact.json",
            "policy_numerical_core.json",
            "result_bundle.json",
            "report_manifest.json",
        )
    else:
        marker_files = (
            "specification.json",
            "dataset_manifest.json",
            "backend_manifest.json",
            "numerical_core.json",
            "result_bundle.json",
            "report_manifest.json",
        )
    for filename in marker_files:
        _assert_markers(_load_json(root / filename), expected, artifact_name=filename)
    specification = _load_json(root / "specification.json")
    dataset_manifest = _load_json(root / "dataset_manifest.json")
    backend_manifest = _load_json(root / "backend_manifest.json")
    observed_backend_id = str(run_manifest.get("backend_manifest_id"))
    expected_backend_id = content_id("backend", backend_manifest)
    if observed_backend_id != expected_backend_id:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Run manifest backend ID does not match backend_manifest.json.",
            stage="artifact.validation",
            context={"expected": expected_backend_id, "observed": observed_backend_id},
        )
    recorded_source_hash = str(backend_manifest.get("dcfa_source_tree_hash", ""))
    current_source_hash = dcfa_source_tree_hash()
    if recorded_source_hash != current_source_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Backend manifest does not match the current DCFA source tree.",
            stage="artifact.validation",
            context={"expected": current_source_hash, "observed": recorded_source_hash},
        )

    if "semisynthetic_numerical_core" in artifact_keys:
        variant = "semisynthetic"
        core_filename = "semisynthetic_numerical_core.json"
        specification_prefix = "semisynth_spec"
        bundle_prefix = "semisynth_bundle"
        run_prefix = "semisynth_run"
    elif expected["track"] == Track.HILLSTROM_POLICY.value:
        variant = "hillstrom_policy"
        core_filename = "policy_numerical_core.json"
        specification_prefix = "policy_spec"
        bundle_prefix = "policy_bundle"
        run_prefix = "hillstrom_run"
    elif str(specification.get("version", "")).startswith("track_t_development_evaluation_v"):
        variant = "track_t_development"
        core_filename = "numerical_core.json"
        specification_prefix = "track_t_dev_spec"
        bundle_prefix = "track_t_dev_bundle"
        run_prefix = "track_t_dev_run"
    else:
        variant = "tabcf"
        core_filename = "numerical_core.json"
        specification_prefix = "spec"
        bundle_prefix = "bundle"
        run_prefix = "run"
    _validate_marker_contract(expected, variant)
    expected_versions = {
        "tabcf": ("tabcf_iv_v1", None),
        "hillstrom_policy": ("hillstrom_policy_v5", "hillstrom_policy_v5"),
        "semisynthetic": ("hillstrom_semisynthetic_v6", "hillstrom_semisynthetic_v6"),
        "track_t_development": (
            "track_t_development_evaluation_v5",
            "track_t_development_evaluation_v5",
        ),
    }
    specification_version, backend_version = expected_versions[variant]
    observed_specification_version = specification.get(
        "specification_version" if variant in {"tabcf", "hillstrom_policy"} else "version"
    )
    if observed_specification_version != specification_version or (
        backend_version is not None and backend_manifest.get("protocol_version") != backend_version
    ):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Saved artifacts use an unsupported or superseded protocol version.",
            stage="artifact.validation",
        )

    numerical_core = _load_json(root / core_filename)
    bundle = _load_json(root / "result_bundle.json")
    expected_specification_id = content_id(specification_prefix, specification)
    _assert_equal_identity(
        name="specification ID",
        expected=expected_specification_id,
        observed_values=(
            ("run_manifest", run_manifest.get("specification_id")),
            ("result_bundle", bundle.get("specification_id")),
            ("numerical_core", numerical_core.get("specification_id")),
        ),
    )
    expected_bundle_id = content_id(bundle_prefix, numerical_core)
    _assert_equal_identity(
        name="result bundle ID",
        expected=expected_bundle_id,
        observed_values=(("result_bundle", bundle.get("result_bundle_id")),),
    )
    dataset_locations: list[tuple[str, Any]] = [
        ("run_manifest", run_manifest.get("dataset_hash")),
        ("result_bundle", bundle.get("dataset_hash")),
        ("dataset_manifest", dataset_manifest.get("dataset_hash")),
        ("numerical_core", numerical_core.get("dataset_hash")),
    ]
    if "dataset_hash" in specification:
        dataset_locations.append(("specification", specification.get("dataset_hash")))
    _assert_equal_identity(
        name="dataset hash",
        expected=str(bundle.get("dataset_hash")),
        observed_values=tuple(dataset_locations),
    )
    if bundle.get("source_artifact") != core_filename:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Result bundle source_artifact does not name its numerical core.",
            stage="artifact.validation",
        )
    observed_source_hash = file_sha256(root / core_filename)
    if bundle.get("source_artifact_hash") != observed_source_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Result bundle is not bound to the current numerical core bytes.",
            stage="artifact.validation",
            context={
                "expected": observed_source_hash,
                "observed": bundle.get("source_artifact_hash"),
            },
        )
    for field in (
        "track",
        "execution_profile",
        "estimator_backend",
        "evidence_status",
        "run_id",
        "specification_id",
        "dataset_hash",
        "warnings",
        "assumptions",
    ):
        _assert_projection(
            name=f"bundle field {field}",
            expected=numerical_core.get(field),
            observed=bundle.get(field),
        )
    try:
        if variant == "tabcf":
            _validate_tabcf_projection(specification, numerical_core, bundle)
        elif variant == "hillstrom_policy":
            _validate_policy_projection(numerical_core, bundle)
        else:
            _assert_projection(
                name=f"{variant} data label",
                expected=numerical_core.get("data_label"),
                observed=bundle.get("data_label"),
            )
            if variant == "semisynthetic":
                _assert_projection(
                    name="semi-synthetic split manifest ID",
                    expected=numerical_core.get("split_manifest_id"),
                    observed=bundle.get("split_manifest_id"),
                )
            _validate_aggregate_projection(variant, numerical_core, bundle)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Saved result projection has malformed or incomplete core fields.",
            stage="artifact.validation",
        ) from exc

    if variant == "hillstrom_policy":
        policy_artifact = _load_json(root / "policy_artifact.json")
        split_manifest = _load_json(root / "split_manifest.json")
        expected_policy_id = content_id("policy", policy_artifact)
        expected_split_id = content_id("split", split_manifest)
        _assert_equal_identity(
            name="policy ID",
            expected=expected_policy_id,
            observed_values=(
                ("result_bundle", bundle.get("policy_id")),
                ("numerical_core", numerical_core.get("policy_id")),
            ),
        )
        _assert_equal_identity(
            name="policy dataset hash",
            expected=str(bundle.get("dataset_hash")),
            observed_values=(("policy_artifact", policy_artifact.get("dataset_hash")),),
        )
        _assert_equal_identity(
            name="split manifest ID",
            expected=expected_split_id,
            observed_values=(
                ("specification", specification.get("split_manifest_id")),
                ("result_bundle", bundle.get("split_manifest_id")),
                ("numerical_core", numerical_core.get("split_manifest_id")),
                ("policy_artifact", policy_artifact.get("split_manifest_id")),
            ),
        )
        _assert_equal_identity(
            name="split dataset hash",
            expected=str(bundle.get("dataset_hash")),
            observed_values=(("split_manifest", split_manifest.get("dataset_hash")),),
        )
        run_payload = {
            "specification_id": expected_specification_id,
            "dataset_hash": bundle.get("dataset_hash"),
            "policy_id": expected_policy_id,
            "backend_manifest_id": expected_backend_id,
        }
    elif variant == "semisynthetic":
        split_manifest = _load_json(root / "split_manifest.json")
        expected_split_id = content_id("split", split_manifest)
        _assert_equal_identity(
            name="split manifest ID",
            expected=expected_split_id,
            observed_values=(
                ("specification", specification.get("split_manifest_id")),
                ("result_bundle", bundle.get("split_manifest_id")),
                ("numerical_core", numerical_core.get("split_manifest_id")),
            ),
        )
        _assert_equal_identity(
            name="split dataset hash",
            expected=str(bundle.get("dataset_hash")),
            observed_values=(("split_manifest", split_manifest.get("dataset_hash")),),
        )
        replication_ids = tuple(
            str(item.get("result_id"))
            for item in numerical_core.get("replication_results", [])
            if isinstance(item, dict)
        )
        run_payload = {
            "specification_id": expected_specification_id,
            "replication_result_ids": replication_ids,
            "backend_manifest_id": expected_backend_id,
        }
    elif variant == "track_t_development":
        replication_ids = tuple(
            str(item.get("result_bundle_id"))
            for item in numerical_core.get("replications", [])
            if isinstance(item, dict)
        )
        run_payload = {
            "specification_id": expected_specification_id,
            "replication_bundle_ids": replication_ids,
            "backend_manifest_id": expected_backend_id,
        }
    else:
        run_payload = {
            "specification_id": expected_specification_id,
            "dataset_hash": bundle.get("dataset_hash"),
            "backend_manifest_id": expected_backend_id,
        }
    expected_run_id = content_id(run_prefix, run_payload)
    _assert_equal_identity(
        name="run ID",
        expected=expected_run_id,
        observed_values=(
            ("run_manifest", run_manifest.get("run_id")),
            ("result_bundle", bundle.get("run_id")),
            ("numerical_core", numerical_core.get("run_id")),
        ),
    )

    audit_records = _load_jsonl(root / "audit.jsonl")
    evidence_records = _load_jsonl(root / "evidence_records.jsonl")
    if variant == "tabcf" and bundle.get("distribution") is not None:
        exported = _load_json(root / "distribution_results.json")
        by_id = {e["evidence_id"]: e for e in evidence_records}
        expected_export = {
            "result_bundle_id": bundle["result_bundle_id"],
            "track": bundle["track"],
            "evidence_status": bundle["evidence_status"],
            "distribution": bundle["distribution"],
            "evidence": {q["query_id"]: by_id.get(q["evidence_id"]) for q in bundle["queries"]},
            "warnings": bundle["warnings"],
            "assumptions": bundle["assumptions"],
        }
        _assert_projection(name="distribution export", expected=expected_export, observed=exported)
    if not audit_records or not evidence_records:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Audit and evidence ledgers must both be non-empty.",
            stage="artifact.validation",
        )
    observed_audit_ids: set[str] = set()
    for index, record in enumerate(audit_records):
        _assert_markers(record, expected, artifact_name=f"audit.jsonl:{index + 1}")
        expected_audit_id = content_id(
            "audit", {key: value for key, value in record.items() if key != "event_id"}
        )
        observed_audit_id = str(record.get("event_id"))
        if (
            observed_audit_id != expected_audit_id
            or observed_audit_id in observed_audit_ids
            or record.get("sequence") != index
            or record.get("specification_id") != bundle.get("specification_id")
            or record.get("run_id") not in {None, bundle.get("run_id")}
        ):
            raise DCFAError(
                ErrorCode.HASH_MISMATCH,
                "Audit event identity, sequence, or run binding is invalid.",
                stage="artifact.validation",
                context={"line": index + 1},
            )
        observed_audit_ids.add(observed_audit_id)
    for index, record in enumerate(evidence_records):
        _assert_markers(record, expected, artifact_name=f"evidence_records.jsonl:{index + 1}")
        expected_evidence_id = content_id("evidence", {**record, "evidence_id": ""})
        if record.get("evidence_id") != expected_evidence_id:
            raise DCFAError(
                ErrorCode.HASH_MISMATCH,
                "Evidence record content does not match its content-addressed ID.",
                stage="artifact.validation",
                context={
                    "line": index + 1,
                    "expected": expected_evidence_id,
                    "observed": record.get("evidence_id"),
                },
            )

    identity_fields = ("run_id", "specification_id", "dataset_hash")
    identity_mismatches = {
        field: {"run_manifest": run_manifest.get(field), "bundle": bundle.get(field)}
        for field in identity_fields
        if run_manifest.get(field) != bundle.get(field)
    }
    if identity_mismatches:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Run manifest and result bundle identities differ.",
            stage="artifact.validation",
            context={"mismatches": identity_mismatches},
        )
    evidence_by_id = {str(record.get("evidence_id")): record for record in evidence_records}
    estimates = [
        *bundle.get("queries", []),
        *bundle.get("values", []),
        *bundle.get("contrasts", []),
        *bundle.get("experimental_effects", []),
    ]
    estimate_ids = [str(estimate.get("evidence_id")) for estimate in estimates]
    if len(estimate_ids) != len(set(estimate_ids)) or set(estimate_ids) != set(evidence_by_id):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Result bundle estimates and evidence ledger do not have a one-to-one ID mapping.",
            stage="artifact.validation",
        )
    for query in estimates:
        evidence_id = str(query.get("evidence_id"))
        record = evidence_by_id.get(evidence_id)
        if record is None:
            raise DCFAError(
                ErrorCode.EVIDENCE_NOT_FOUND,
                f"Bundle query evidence ID {evidence_id} did not resolve.",
                stage="artifact.validation",
            )
        common_fields = ("value_raw", "value_display", "units")
        tabcf_fields = ("claim_type", "support_status", "warnings") if "query_id" in query else ()
        for field in (*common_fields, *tabcf_fields):
            if query.get(field) != record.get(field):
                raise DCFAError(
                    ErrorCode.EVIDENCE_MISMATCH,
                    f"Bundle query and evidence differ on {field}.",
                    stage="artifact.validation",
                    context={"evidence_id": evidence_id, "field": field},
                )
        if "query_id" not in query and record.get("warnings") != bundle.get("warnings"):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Policy bundle warnings differ from its evidence record.",
                stage="artifact.validation",
                context={"evidence_id": evidence_id},
            )
        if "query_id" not in query:
            if variant == "hillstrom_policy":
                if "baseline_policy_name" in query:
                    expected_claim_type = (
                        f"paired_policy_contrast:{query['policy_name']}:minus:"
                        f"{query['baseline_policy_name']}:{query['method']}"
                    )
                elif "outcome" in query:
                    expected_claim_type = (
                        f"randomized_arm_effect:{query['outcome']}:{query['action']}:minus:"
                        f"{query['baseline_action']}"
                    )
                else:
                    expected_claim_type = f"policy_value:{query['policy_name']}:{query['method']}"
            elif variant == "semisynthetic":
                expected_claim_type = (
                    f"semisynthetic:{query['scenario']}:{query['metric']}:replication_mean"
                )
            else:
                expected_claim_type = (
                    f"development_oracle_metric:{query['scenario']}:{query['metric']}"
                )
            if (
                record.get("claim_type") != expected_claim_type
                or record.get("support_status") != "supported"
            ):
                raise DCFAError(
                    ErrorCode.EVIDENCE_MISMATCH,
                    "Aggregate estimate claim type or support status differs from evidence.",
                    stage="artifact.validation",
                    context={"evidence_id": evidence_id},
                )
        if record.get("source_artifact_hash") != bundle.get("source_artifact_hash"):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Evidence source artifact hash does not match the result bundle.",
                stage="artifact.validation",
                context={"evidence_id": evidence_id},
            )
        evidence_identity = {
            "run_id": bundle.get("run_id"),
            "dataset_hash": bundle.get("dataset_hash"),
            "specification_id": bundle.get("specification_id"),
            "result_bundle_id": bundle.get("result_bundle_id"),
            "source_artifact": bundle.get("source_artifact"),
            "source_artifact_hash": bundle.get("source_artifact_hash"),
        }
        evidence_mismatches = {
            field: {"expected": value, "observed": record.get(field)}
            for field, value in evidence_identity.items()
            if record.get(field) != value
        }
        if evidence_mismatches:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Evidence identity does not match its result bundle.",
                stage="artifact.validation",
                context={"evidence_id": evidence_id, "mismatches": evidence_mismatches},
            )

    report_manifest = _load_json(root / "report_manifest.json")
    if report_manifest.get("result_bundle_id") != bundle.get("result_bundle_id") or set(
        str(value) for value in report_manifest.get("evidence_ids", [])
    ) != set(estimate_ids):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Report manifest does not resolve the complete validated result bundle.",
            stage="artifact.validation",
        )
    report_hash = file_sha256(root / "report.md")
    if "report_hash" in report_manifest and report_manifest.get("report_hash") != report_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Report manifest hash does not match report.md.",
            stage="artifact.validation",
        )
    if "plot_hash" in report_manifest:
        plot_path = root / "interventional_summary.png"
        if not plot_path.is_file() or report_manifest.get("plot_hash") != file_sha256(plot_path):
            raise DCFAError(
                ErrorCode.HASH_MISMATCH,
                "Report manifest plot hash does not match the saved plot.",
                stage="artifact.validation",
            )
    if "source_artifact" in report_manifest and (
        report_manifest.get("source_artifact") != bundle.get("source_artifact")
        or report_manifest.get("source_artifact_hash") != bundle.get("source_artifact_hash")
    ):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Report manifest source binding differs from the validated result bundle.",
            stage="artifact.validation",
        )

    report_text = (root / "report.md").read_text(encoding="utf-8")
    for query in estimates:
        if (
            str(query["evidence_id"]) not in report_text
            or str(query["value_display"]) not in report_text
        ):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Markdown report omitted an evidence ID or its validated display value.",
                stage="artifact.validation",
                context={"query_id": query.get("query_id")},
            )
        uncertainty_fields = (
            ("interval_lower", "interval_upper")
            if "interval_lower" in query and "interval_upper" in query
            else (("standard_error",) if "standard_error" in query else ())
        )
        for field in uncertainty_fields:
            if field in query and format(float(query[field]), ".6g") not in report_text:
                raise DCFAError(
                    ErrorCode.EVIDENCE_MISMATCH,
                    f"Markdown report omitted validated uncertainty field {field}.",
                    stage="artifact.validation",
                    context={"evidence_id": query.get("evidence_id")},
                )
    for warning in bundle.get("warnings", []):
        if (
            str(warning.get("code")) not in report_text
            or str(warning.get("message")) not in report_text
        ):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Markdown report omitted a validated warning.",
                stage="artifact.validation",
                context={"warning_code": warning.get("code")},
            )
    for assumption in bundle.get("assumptions", []):
        if str(assumption) not in report_text:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Markdown report omitted a validated assumption.",
                stage="artifact.validation",
            )
    for allocation in bundle.get("action_allocations", []):
        if len(allocation) != 3 or any(
            value not in report_text
            for value in (
                str(allocation[0]),
                str(allocation[1]),
                format(float(allocation[2]), ".6g"),
            )
        ):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Markdown report omitted a frozen action allocation.",
                stage="artifact.validation",
            )
    for feature, value in bundle.get("baseline_balance", []):
        if str(feature) not in report_text or format(float(value), ".6g") not in report_text:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Markdown report omitted a baseline-balance diagnostic.",
                stage="artifact.validation",
            )
    return {
        "status": "valid",
        "run_id": run_manifest.get("run_id"),
        "result_bundle_id": bundle.get("result_bundle_id"),
        "verified_artifacts": tuple(sorted(verified_hashes)),
        "evidence_count": len(evidence_records),
        **expected,
    }


def verify_agent_benchmark_file(path: Path, cases_path: Path) -> dict[str, Any]:
    """Recompute a recorded Track A summary and bind it to the exact case file."""
    from dcfa.agent.benchmark import (  # Local import keeps ordinary artifact checks light.
        RECORDED_FIXTURE_VALUE,
        BenchmarkTrace,
        _trace_grade_outcome,
        benchmark_summary,
        load_benchmark_cases,
    )

    payload = _load_json(Path(path))
    expected_markers = {
        "track": Track.AGENT_BENCHMARK.value,
        "execution_profile": ExecutionProfile.TEST.value,
        "estimator_backend": EstimatorBackend.MOCK.value,
        "evidence_status": EvidenceStatus.TEST_ONLY.value,
    }
    _assert_markers(payload, expected_markers, artifact_name=Path(path).name)
    if payload.get("benchmark_protocol_version") != "track_a_recorded_v4":
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Unsupported recorded benchmark protocol version.",
            stage="agent_benchmark.validation",
        )
    if payload.get("case_version") != "track_a_cases_v1":
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Benchmark case version mismatch.",
            stage="agent_benchmark.validation",
        )
    case_path = Path(cases_path)
    if payload.get("case_file_hash") != file_sha256(case_path):
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Benchmark output does not match the supplied case file.",
            stage="agent_benchmark.validation",
        )
    cases = load_benchmark_cases(case_path)
    raw_traces = payload.get("traces")
    if not isinstance(raw_traces, list):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Benchmark traces must be a JSON list.",
            stage="agent_benchmark.validation",
        )
    tuple_fields = {
        "warning_codes",
        "evidence_ids",
        "values",
        "grader_failures",
    }
    try:
        traces = tuple(
            BenchmarkTrace(
                **{
                    key: tuple(value) if key in tuple_fields else value
                    for key, value in raw.items()
                }
            )
            for raw in raw_traces
        )
    except (TypeError, ValueError, AttributeError) as exc:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Benchmark trace schema validation failed.",
            stage="agent_benchmark.validation",
        ) from exc
    case_ids = {case.case_id for case in cases}
    if {trace.case_id for trace in traces} != case_ids:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Benchmark trace case IDs differ from the supplied case manifest.",
            stage="agent_benchmark.validation",
        )
    cases_by_id = {case.case_id: case for case in cases}
    for trace in traces:
        case = cases_by_id[trace.case_id]
        immutable_fields = {
            "family": case.family,
            "fixture_behavior": case.fixture_behavior,
            "expected_final_state": case.expected_final_state,
            "expected_max_analyze_calls": case.expected_max_analyze_calls,
        }
        mismatched_fields = [
            name
            for name, expected_value in immutable_fields.items()
            if getattr(trace, name) != expected_value
        ]
        if mismatched_fields:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Benchmark trace does not match its frozen case definition.",
                stage="agent_benchmark.validation",
                context={
                    "case_id": trace.case_id,
                    "run_index": trace.run_index,
                    "system": trace.system,
                    "mismatched_fields": mismatched_fields,
                },
            )
        numerical_fidelity, grader_failures = _trace_grade_outcome(
            case,
            final_state=trace.final_state,
            error_code=trace.error_code,
            analyze_calls=trace.analyze_calls,
            warning_codes=trace.warning_codes,
            evidence_ids=trace.evidence_ids,
            values=trace.values,
            fixture_value=RECORDED_FIXTURE_VALUE,
        )
        if (
            trace.numerical_fidelity != numerical_fidelity
            or trace.valid_completion != (not grader_failures)
            or trace.grader_failures != grader_failures
        ):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Benchmark trace grader outcome does not match the frozen grading rules.",
                stage="agent_benchmark.validation",
                context={
                    "case_id": trace.case_id,
                    "run_index": trace.run_index,
                    "system": trace.system,
                },
            )
    runs = int(payload.get("runs_per_case", 0))
    if runs < 1 or len(traces) != len(cases) * runs * 2:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Benchmark trace cardinality does not match cases, runs, and systems.",
            stage="agent_benchmark.validation",
        )
    expected_runs = set(range(runs))
    for case_id in case_ids:
        for system in ("fixed_workflow", "full_agent"):
            observed_runs = {
                trace.run_index
                for trace in traces
                if trace.case_id == case_id and trace.system == system
            }
            if observed_runs != expected_runs:
                raise DCFAError(
                    ErrorCode.EVIDENCE_MISMATCH,
                    "Benchmark runs are missing, duplicated, or assigned to an unknown system.",
                    stage="agent_benchmark.validation",
                    context={"case_id": case_id, "system": system},
                )
    recomputed = to_primitive(benchmark_summary(traces))
    mismatches = {
        key: {"expected": value, "observed": payload.get(key)}
        for key, value in recomputed.items()
        if payload.get(key) != value
    }
    if mismatches:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Recorded benchmark summary does not match its raw traces.",
            stage="agent_benchmark.validation",
            context={"mismatched_fields": sorted(mismatches)},
        )
    return {
        "status": "valid",
        "benchmark_id": payload["benchmark_id"],
        "benchmark_protocol_version": payload["benchmark_protocol_version"],
        "case_count": len(cases),
        "runs_per_case": runs,
        **expected_markers,
    }
