"""Immutable v1 specifications, manifests, diagnostics, and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dcfa.canonical import content_id
from dcfa.constants import (
    EstimatorBackend,
    EvidenceStatus,
    ExecutionProfile,
    SupportStatus,
    Track,
    WarningSeverity,
)


@dataclass(frozen=True)
class CausalRoles:
    outcome: str
    treatment: str
    instrument: str
    baseline_covariates: tuple[str, ...] = ()
    treatment_type: str = "continuous"


@dataclass(frozen=True)
class QuerySpecification:
    query_id: str
    kind: str
    x: float
    comparison_x: float | None = None
    level: float | None = None
    threshold: float | None = None
    units: str = "outcome_units"


@dataclass(frozen=True)
class DistributionRequest:
    """Two original-unit interventions on explicitly already-log stored columns."""

    prices: tuple[float, float]
    treatment_units: str
    outcome_units: str
    threshold: float | None = None
    treatment_scale: str = "stored_natural_log"
    outcome_scale: str = "stored_natural_log"
    quantile_levels: tuple[float, ...] = (0.25, 0.50, 0.75)


@dataclass(frozen=True)
class AnalysisSpecification:
    dataset_hash: str
    roles: CausalRoles
    queries: tuple[QuerySpecification, ...]
    intervention_grid: tuple[float, ...]
    quantile_levels: tuple[float, ...] = (0.1, 0.5, 0.9)
    risk_thresholds: tuple[float, ...] = ()
    execution_profile: ExecutionProfile = ExecutionProfile.LOCAL_DEVELOPMENT
    estimator_backend: EstimatorBackend = EstimatorBackend.SKLEARN_QUANTILE_FALLBACK
    evidence_status: EvidenceStatus = EvidenceStatus.DEVELOPMENT_ONLY
    track: Track = Track.TABCF_IV
    support_policy: str = "strict"
    confirmed_by_user: bool = True
    seed: int = 1729
    backend_parameters: tuple[tuple[str, str], ...] = ()
    specification_version: str = "tabcf_iv_v1"
    distribution: DistributionRequest | None = None

    @property
    def specification_id(self) -> str:
        return content_id("spec", self)


@dataclass(frozen=True)
class WarningRecord:
    code: str
    message: str
    severity: WarningSeverity
    source: str


@dataclass(frozen=True)
class SupportAssessment:
    x: float
    status: SupportStatus
    coverage_score: float
    recommended_interval: tuple[float, float]
    strict_interval: tuple[float, float]
    reason: str


@dataclass(frozen=True)
class DiagnosticBundle:
    first_stage_f: float
    first_stage_r2: float
    control_rank_cvm: float
    control_rank_mean: float
    residual_dependence_score: float
    interpretation: str = (
        "These are empirical diagnostics. They do not prove instrument validity or identification."
    )


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    dataset_hash: str
    source: str
    source_kind: str
    row_count: int
    columns: tuple[str, ...]
    generation_seed: int | None
    dgp_label: str | None
    dgp_mapping_status: str
    license_note: str
    track: Track
    execution_profile: ExecutionProfile
    estimator_backend: EstimatorBackend
    evidence_status: EvidenceStatus


@dataclass(frozen=True)
class BackendManifest:
    track: Track
    estimator_backend: EstimatorBackend
    execution_profile: ExecutionProfile
    evidence_status: EvidenceStatus
    model_class_mean: str
    model_class_distribution: str
    parameters: tuple[tuple[str, Any], ...]
    quantile_grid: tuple[float, ...]
    seed: int
    package_versions: tuple[tuple[str, str], ...]
    cdf_rule: str
    quantile_monotonicity_rule: str
    upstream_source_commit: str
    dcfa_source_tree_hash: str
    model_artifact_hash: str = "not_applicable"
    runtime_image_digest: str = "local_environment_not_release_eligible"

    @property
    def backend_manifest_id(self) -> str:
        return content_id("backend", self)


@dataclass(frozen=True)
class QueryResult:
    query_id: str
    claim_type: str
    value_raw: float
    value_display: str
    units: str
    support_status: SupportStatus
    warnings: tuple[WarningRecord, ...]
    evidence_id: str


@dataclass(frozen=True)
class ResultBundle:
    result_bundle_id: str
    run_id: str
    specification_id: str
    dataset_hash: str
    track: Track
    execution_profile: ExecutionProfile
    estimator_backend: EstimatorBackend
    evidence_status: EvidenceStatus
    x_grid: tuple[float, ...]
    y_grid: tuple[float, ...]
    interventional_cdf: tuple[tuple[float, ...], ...]
    interventional_mean: tuple[float, ...]
    quantile_levels: tuple[float, ...]
    interventional_quantiles: tuple[tuple[float, ...], ...]
    risk_thresholds: tuple[float, ...]
    interventional_risks: tuple[tuple[float, ...], ...]
    diagnostics: DiagnosticBundle
    support: tuple[SupportAssessment, ...]
    warnings: tuple[WarningRecord, ...]
    assumptions: tuple[str, ...]
    queries: tuple[QueryResult, ...]
    source_artifact: str
    source_artifact_hash: str
    cached: bool = False
    distribution: dict[str, Any] | None = None


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    track: Track
    evidence_status: EvidenceStatus
    estimator_backend: EstimatorBackend
    execution_profile: ExecutionProfile
    run_id: str
    dataset_hash: str
    specification_id: str
    result_bundle_id: str
    claim_type: str
    value_raw: float
    value_display: str
    units: str
    support_status: SupportStatus
    warnings: tuple[WarningRecord, ...]
    source_artifact: str
    source_artifact_hash: str


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    specification_id: str
    dataset_hash: str
    backend_manifest_id: str
    track: Track
    execution_profile: ExecutionProfile
    estimator_backend: EstimatorBackend
    evidence_status: EvidenceStatus
    seed: int
    artifact_hashes: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PolicyValueEstimate:
    policy_name: str
    method: str
    value_raw: float
    standard_error: float
    interval_lower: float
    interval_upper: float
    value_display: str
    units: str
    evidence_id: str


@dataclass(frozen=True)
class PolicyContrastEstimate:
    policy_name: str
    baseline_policy_name: str
    method: str
    value_raw: float
    standard_error: float
    interval_lower: float
    interval_upper: float
    value_display: str
    units: str
    evidence_id: str


@dataclass(frozen=True)
class RCTEffectEstimate:
    outcome: str
    action: str
    baseline_action: str
    value_raw: float
    standard_error: float
    interval_lower: float
    interval_upper: float
    value_display: str
    units: str
    evidence_id: str


@dataclass(frozen=True)
class PolicyEvaluationBundle:
    result_bundle_id: str
    run_id: str
    specification_id: str
    dataset_hash: str
    track: Track
    execution_profile: ExecutionProfile
    estimator_backend: EstimatorBackend
    evidence_status: EvidenceStatus
    policy_id: str
    split_manifest_id: str
    outcome: str
    horizon: str
    test_row_count: int
    action_costs: tuple[float, float, float]
    capacity_fraction: float | None
    values: tuple[PolicyValueEstimate, ...]
    contrasts: tuple[PolicyContrastEstimate, ...]
    experimental_effects: tuple[RCTEffectEstimate, ...]
    action_allocations: tuple[tuple[str, int, float], ...]
    dataset_arm_counts: tuple[tuple[str, int], ...]
    missingness_status: str
    baseline_balance: tuple[tuple[str, float], ...]
    warnings: tuple[WarningRecord, ...]
    assumptions: tuple[str, ...]
    source_artifact: str
    source_artifact_hash: str


@dataclass(frozen=True)
class SemiSyntheticEstimate:
    scenario: str
    metric: str
    replication_count: int
    value_raw: float
    standard_error: float
    value_display: str
    units: str
    evidence_id: str


@dataclass(frozen=True)
class SemiSyntheticEvaluationBundle:
    result_bundle_id: str
    run_id: str
    specification_id: str
    dataset_hash: str
    track: Track
    execution_profile: ExecutionProfile
    estimator_backend: EstimatorBackend
    evidence_status: EvidenceStatus
    split_manifest_id: str
    data_label: str
    values: tuple[SemiSyntheticEstimate, ...]
    warnings: tuple[WarningRecord, ...]
    assumptions: tuple[str, ...]
    source_artifact: str
    source_artifact_hash: str


@dataclass(frozen=True)
class TrackTEvaluationEstimate:
    scenario: str
    metric: str
    seed_count: int
    value_raw: float
    standard_error: float
    value_display: str
    units: str
    evidence_id: str


@dataclass(frozen=True)
class TrackTDevelopmentEvaluationBundle:
    result_bundle_id: str
    run_id: str
    specification_id: str
    dataset_hash: str
    track: Track
    execution_profile: ExecutionProfile
    estimator_backend: EstimatorBackend
    evidence_status: EvidenceStatus
    data_label: str
    values: tuple[TrackTEvaluationEstimate, ...]
    warnings: tuple[WarningRecord, ...]
    assumptions: tuple[str, ...]
    source_artifact: str
    source_artifact_hash: str
