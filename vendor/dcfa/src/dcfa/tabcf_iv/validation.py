"""Fail-closed validation for the public TabCF Analyst v1 boundary."""

from __future__ import annotations

from collections.abc import Mapping
from numbers import Real

import numpy as np

from dcfa.canonical import dataset_sha256, is_sha256_digest
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import DCFAError, ErrorCode
from dcfa.schemas import AnalysisSpecification, DatasetManifest
from dcfa.tabcf_iv.local_tabpfn import LOCAL_TABPFN_V2_BACKEND_PARAMETERS
from dcfa.tabcf_iv.managed_client import MANAGED_BACKEND_PARAMETERS


def _is_numeric_scalar(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def validate_tabcf_specification(specification: AnalysisSpecification) -> None:
    """Validate every no-fit condition before a backend is constructed."""
    if specification.track is not Track.TABCF_IV:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "The public TabCF adapter accepts only track=tabcf_iv.",
            stage="specification.validation",
        )

    roles = specification.roles
    if roles.baseline_covariates:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BASELINE_COVARIATES,
            "TabCF Analyst v1 does not support baseline covariates; fitting was not started.",
            stage="specification.validation",
            context={"baseline_covariates": list(roles.baseline_covariates)},
        )
    if roles.treatment_type != "continuous":
        raise DCFAError(
            ErrorCode.UNSUPPORTED_TREATMENT,
            "TabCF Analyst v1 requires one continuous treatment.",
            stage="specification.validation",
            context={"treatment_type": roles.treatment_type},
        )
    role_names = (roles.outcome, roles.treatment, roles.instrument)
    if any(
        not isinstance(name, str) or not name.strip() or name != name.strip() for name in role_names
    ):
        raise DCFAError(
            ErrorCode.MISSING_CAUSAL_ROLE,
            "Outcome, treatment, and instrument roles must be explicit and whitespace-normalized.",
            stage="specification.validation",
        )
    if len(set(role_names)) != 3:
        raise DCFAError(
            ErrorCode.ROLE_CONFLICT,
            "Outcome, treatment, and instrument must name three distinct columns.",
            stage="specification.validation",
        )
    if not specification.confirmed_by_user:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "The immutable causal specification has not been confirmed.",
            stage="specification.validation",
        )
    if specification.support_policy != "strict":
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "TabCF Analyst v1 requires support_policy='strict'.",
            stage="specification.validation",
        )
    if specification.specification_version != "tabcf_iv_v1":
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "The public adapter accepts only specification_version='tabcf_iv_v1'.",
            stage="specification.validation",
        )
    if not specification.intervention_grid:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "At least one intervention value is required.",
            stage="specification.validation",
        )
    numeric_grids = (
        specification.intervention_grid,
        specification.quantile_levels,
        specification.risk_thresholds,
    )
    if any(not _is_numeric_scalar(value) for values in numeric_grids for value in values):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Intervention, quantile, and risk grids must contain numeric scalar values.",
            stage="specification.validation",
        )
    try:
        grid = np.asarray(specification.intervention_grid, dtype=float)
        quantile_levels = np.asarray(specification.quantile_levels, dtype=float)
        risk_thresholds = np.asarray(specification.risk_thresholds, dtype=float)
    except (TypeError, ValueError) as exc:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Intervention, quantile, and risk grids must be one-dimensional numeric values.",
            stage="specification.validation",
        ) from exc
    if grid.ndim != 1 or quantile_levels.ndim != 1 or risk_thresholds.ndim != 1:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Intervention, quantile, and risk grids must be one-dimensional.",
            stage="specification.validation",
        )
    if not np.all(np.isfinite(grid)):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "intervention_grid must contain only finite values.",
            stage="specification.validation",
        )
    if tuple(sorted(set(specification.intervention_grid))) != specification.intervention_grid:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "intervention_grid must be strictly increasing and contain no duplicates.",
            stage="specification.validation",
        )
    if any(not np.isfinite(level) or level <= 0.0 or level >= 1.0 for level in quantile_levels):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Quantile levels must be strictly inside (0, 1).",
            stage="specification.validation",
        )
    if tuple(sorted(set(specification.quantile_levels))) != specification.quantile_levels:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "quantile_levels must be strictly increasing and contain no duplicates.",
            stage="specification.validation",
        )
    if any(not np.isfinite(threshold) for threshold in risk_thresholds):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "risk_thresholds must contain only finite values.",
            stage="specification.validation",
        )
    if tuple(sorted(set(specification.risk_thresholds))) != specification.risk_thresholds:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "risk_thresholds must be strictly increasing and contain no duplicates.",
            stage="specification.validation",
        )
    if specification.distribution is not None:
        import math

        from dcfa.tabcf_iv.distribution import validate_distribution_request

        d = specification.distribution
        validate_distribution_request(d)
        if (
            specification.intervention_grid != tuple(math.log(p) for p in d.prices)
            or specification.quantile_levels != d.quantile_levels
            or specification.risk_thresholds
            != ((math.log(d.threshold),) if d.threshold is not None else ())
            or len(specification.queries) != 1
            or specification.queries[0].kind != "distribution"
        ):
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                "Distribution specification does not match its exact-unit request.",
                stage="specification.units",
            )
    elif any(q.kind == "distribution" for q in specification.queries):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Missing distribution request.",
            stage="specification.units",
        )
    supported_query_kinds = {
        "distribution",
        "mean",
        "quantile",
        "risk",
        "mean_contrast",
        "quantile_contrast",
        "risk_contrast",
    }
    query_ids = [query.query_id for query in specification.queries]
    if not query_ids:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "At least one evidence-linked query is required.",
            stage="specification.validation",
        )
    if any(
        not isinstance(query_id, str) or not query_id.strip() or query_id != query_id.strip()
        for query_id in query_ids
    ):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Query IDs must be non-empty and whitespace-normalized.",
            stage="specification.validation",
        )
    if len(query_ids) != len(set(query_ids)):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Query IDs must be unique within an immutable specification.",
            stage="specification.validation",
        )
    for query in specification.queries:
        query_numeric_values = (query.x, query.comparison_x, query.level, query.threshold)
        try:
            invalid_numeric = not _is_numeric_scalar(query.x) or any(
                value is not None
                and (not _is_numeric_scalar(value) or not np.isfinite(float(value)))
                for value in query_numeric_values
            )
        except (TypeError, ValueError):
            invalid_numeric = True
        if invalid_numeric:
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                f"Query {query.query_id} contains a non-finite numerical field.",
                stage="specification.validation",
            )
        if (
            not isinstance(query.units, str)
            or not query.units.strip()
            or query.units != query.units.strip()
        ):
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                f"Query {query.query_id} units must be explicit and whitespace-normalized.",
                stage="specification.validation",
            )
        if not isinstance(query.kind, str) or query.kind not in supported_query_kinds:
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                f"Unsupported query kind: {query.kind}.",
                stage="specification.validation",
            )
        if float(np.min(np.abs(grid - query.x))) > 1e-10:
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                f"Query {query.query_id} x is absent from intervention_grid.",
                stage="specification.validation",
            )
        if query.kind.endswith("_contrast"):
            if (
                query.comparison_x is None
                or float(np.min(np.abs(grid - query.comparison_x))) > 1e-10
            ):
                raise DCFAError(
                    ErrorCode.INVALID_SPECIFICATION,
                    f"Query {query.query_id} comparison_x is absent from intervention_grid.",
                    stage="specification.validation",
                )
        if query.kind in {"quantile", "quantile_contrast"}:
            if query.level is None or not any(
                abs(level - query.level) <= 1e-10 for level in specification.quantile_levels
            ):
                raise DCFAError(
                    ErrorCode.INVALID_SPECIFICATION,
                    f"Query {query.query_id} quantile level is absent from quantile_levels.",
                    stage="specification.validation",
                )
        if query.kind in {"risk", "risk_contrast"}:
            if query.threshold is None or not any(
                abs(threshold - query.threshold) <= 1e-10
                for threshold in specification.risk_thresholds
            ):
                raise DCFAError(
                    ErrorCode.INVALID_SPECIFICATION,
                    f"Query {query.query_id} threshold is absent from risk_thresholds.",
                    stage="specification.validation",
                )
    if any(
        not isinstance(pair, tuple)
        or len(pair) != 2
        or not isinstance(pair[0], str)
        or not pair[0].strip()
        or pair[0] != pair[0].strip()
        or not isinstance(pair[1], str)
        for pair in specification.backend_parameters
    ):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "backend_parameters must be normalized string name/value pairs.",
            stage="specification.validation",
        )
    parameter_names = [name for name, _value in specification.backend_parameters]
    if len(parameter_names) != len(set(parameter_names)):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "backend_parameters must not contain duplicate names.",
            stage="specification.validation",
        )
    if specification.estimator_backend is EstimatorBackend.SKLEARN_QUANTILE_FALLBACK:
        if (
            specification.execution_profile is not ExecutionProfile.LOCAL_DEVELOPMENT
            or specification.evidence_status is not EvidenceStatus.DEVELOPMENT_ONLY
        ):
            raise DCFAError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Fallback specifications must be local_development and development_only.",
                stage="specification.validation",
            )
        if specification.backend_parameters:
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                "The fixed sklearn fallback does not accept per-run backend parameters.",
                stage="specification.validation",
            )
    elif specification.estimator_backend is EstimatorBackend.TABPFN:
        parameters = dict(specification.backend_parameters)
        if parameters.get("access_mode") == "managed_client":
            if tuple(specification.backend_parameters) != MANAGED_BACKEND_PARAMETERS:
                raise DCFAError(
                    ErrorCode.INVALID_SPECIFICATION,
                    "Managed TabPFN requires the exact frozen client parameters.",
                    stage="specification.validation",
                )
            if (
                specification.execution_profile is not ExecutionProfile.LOCAL_DEVELOPMENT
                or specification.evidence_status is not EvidenceStatus.DEVELOPMENT_ONLY
            ):
                raise DCFAError(
                    ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                    "Managed TabPFN is restricted to local_development/development_only.",
                    stage="specification.validation",
                )
            return
        if parameters.get("access_mode") == "local_model":
            if tuple(specification.backend_parameters) != LOCAL_TABPFN_V2_BACKEND_PARAMETERS:
                raise DCFAError(
                    ErrorCode.INVALID_SPECIFICATION,
                    "Local TabPFN v2 requires the exact frozen deployment parameters.",
                    stage="specification.validation",
                )
            if (
                specification.execution_profile is not ExecutionProfile.LOCAL_DEVELOPMENT
                or specification.evidence_status is not EvidenceStatus.DEVELOPMENT_ONLY
            ):
                raise DCFAError(
                    ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                    "Local TabPFN v2 is restricted to local_development/development_only.",
                    stage="specification.validation",
                )
            return
        allowed_parameters = {
            "model_path",
            "model_artifact_hash",
            "runtime_image_digest",
        }
        unknown = sorted(set(parameter_names) - allowed_parameters)
        if unknown:
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                "TabPFN backend_parameters contain unsupported names.",
                stage="specification.validation",
                context={"unknown_parameters": unknown},
            )
        expected_evidence_status = (
            EvidenceStatus.ELIGIBLE_FOR_RELEASE
            if specification.execution_profile is ExecutionProfile.LOCKED_EVALUATION
            else EvidenceStatus.DEVELOPMENT_ONLY
        )
        if (
            specification.execution_profile
            not in {ExecutionProfile.LOCAL_DEVELOPMENT, ExecutionProfile.LOCKED_EVALUATION}
            or specification.evidence_status is not expected_evidence_status
        ):
            raise DCFAError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "TabPFN profile and evidence status do not form an allowed execution contract.",
                stage="specification.validation",
            )
    else:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "The TabCF adapter accepts only sklearn_quantile_fallback or tabpfn.",
            stage="specification.validation",
        )


def validate_tabcf_data(
    data: Mapping[str, np.ndarray],
    specification: AnalysisSpecification,
) -> dict[str, np.ndarray]:
    roles = specification.roles
    required = (roles.instrument, roles.treatment, roles.outcome)
    missing = [name for name in required if name not in data]
    if missing:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            f"Dataset is missing required role columns: {missing}.",
            stage="data.validation",
            context={"missing_columns": missing},
        )
    arrays = {name: np.asarray(data[name], dtype=float).reshape(-1) for name in required}
    row_counts = {len(values) for values in arrays.values()}
    if len(row_counts) != 1 or not row_counts or next(iter(row_counts)) < 40:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Role columns must have the same length and contain at least 40 rows.",
            stage="data.validation",
        )
    for name, values in arrays.items():
        if not np.all(np.isfinite(values)):
            raise DCFAError(
                ErrorCode.INVALID_DATA,
                f"Column {name} contains non-finite values.",
                stage="data.validation",
                context={"column": name},
            )
        if float(np.ptp(values)) == 0.0:
            raise DCFAError(
                ErrorCode.INVALID_DATA,
                f"Column {name} is constant.",
                stage="data.validation",
                context={"column": name},
            )
    observed_hash = dataset_sha256(arrays)
    if observed_hash != specification.dataset_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "The supplied role arrays do not match the immutable specification dataset hash.",
            stage="data.validation",
            context={"expected": specification.dataset_hash, "observed": observed_hash},
        )
    return arrays


def validate_tabcf_dataset_manifest(
    manifest: DatasetManifest,
    specification: AnalysisSpecification,
    arrays: Mapping[str, np.ndarray],
) -> None:
    """Bind manifest identity and markers to the already validated role arrays."""
    expected_markers = (
        specification.track,
        specification.execution_profile,
        specification.estimator_backend,
        specification.evidence_status,
    )
    observed_markers = (
        manifest.track,
        manifest.execution_profile,
        manifest.estimator_backend,
        manifest.evidence_status,
    )
    if observed_markers != expected_markers:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "Dataset manifest execution/evidence markers differ from the specification.",
            stage="data.manifest_validation",
        )
    if manifest.dataset_hash != specification.dataset_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Dataset manifest hash does not match the immutable specification.",
            stage="data.manifest_validation",
        )
    provenance_fields = (
        manifest.dataset_id,
        manifest.source,
        manifest.source_kind,
        manifest.dgp_mapping_status,
        manifest.license_note,
    )
    if any(
        not isinstance(value, str) or not value.strip() for value in provenance_fields
    ) or not is_sha256_digest(manifest.dataset_hash):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Dataset manifest provenance is incomplete or its dataset hash is malformed.",
            stage="data.manifest_validation",
        )
    role_columns = {
        specification.roles.instrument,
        specification.roles.treatment,
        specification.roles.outcome,
    }
    if (
        manifest.row_count != len(next(iter(arrays.values())))
        or len(manifest.columns) != len(role_columns)
        or set(manifest.columns) != role_columns
        or any(
            not isinstance(column, str) or not column.strip() or column != column.strip()
            for column in manifest.columns
        )
    ):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Dataset manifest row count or canonical role columns do not match the supplied data.",
            stage="data.manifest_validation",
            context={
                "manifest_row_count": manifest.row_count,
                "observed_row_count": len(next(iter(arrays.values()))),
                "manifest_columns": list(manifest.columns),
                "role_columns": sorted(role_columns),
            },
        )
