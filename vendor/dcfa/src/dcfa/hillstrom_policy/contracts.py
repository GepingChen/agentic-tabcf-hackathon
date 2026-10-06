"""Immutable contracts for the categorical-action Hillstrom evidence track."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dcfa.canonical import content_id
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track

HILLSTROM_ACTIONS = ("no_email", "mens_email", "womens_email")
POST_TREATMENT_COLUMNS = frozenset({"visit", "conversion", "spend"})


@dataclass(frozen=True)
class HillstromDataManifest:
    dataset_id: str
    dataset_hash: str
    exact_source: str
    retrieval_date: str
    raw_file_hash: str
    row_count: int
    column_names: tuple[str, ...]
    arm_counts: tuple[tuple[str, int], ...]
    encoding_map: tuple[tuple[str, str], ...]
    license_note: str
    source_kind: str
    track: Track = Track.HILLSTROM_POLICY
    execution_profile: ExecutionProfile = ExecutionProfile.LOCAL_DEVELOPMENT
    estimator_backend: EstimatorBackend = EstimatorBackend.SKLEARN_POLICY
    evidence_status: EvidenceStatus = EvidenceStatus.DEVELOPMENT_ONLY


@dataclass(frozen=True)
class HillstromDataset:
    """Raw, immutable columns. Preprocessing is intentionally split-scoped."""

    feature_columns: tuple[tuple[str, tuple[Any, ...]], ...]
    actions: tuple[int, ...]
    spend: tuple[float, ...]
    conversion: tuple[float, ...]
    visit: tuple[float, ...]
    manifest: HillstromDataManifest

    @property
    def row_count(self) -> int:
        return len(self.actions)

    @property
    def feature_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.feature_columns)


@dataclass(frozen=True)
class SplitManifest:
    dataset_hash: str
    seed: int
    stratified_by: str
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    ratios: tuple[float, float, float] = (0.6, 0.2, 0.2)

    @property
    def split_manifest_id(self) -> str:
        return content_id("split", self)


@dataclass(frozen=True)
class PreprocessingArtifact:
    fit_split: str
    fit_indices_hash: str
    raw_feature_names: tuple[str, ...]
    encoded_feature_names: tuple[str, ...]
    numeric_parameters: tuple[tuple[str, float, float, float], ...]
    categorical_levels: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def preprocessing_id(self) -> str:
        return content_id("preprocess", self)


@dataclass(frozen=True)
class PolicyObjective:
    outcome: str = "spend"
    horizon: str = "two_weeks"
    margin: float = 1.0
    action_costs: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class HillstromPolicySpecification:
    dataset_hash: str
    split_manifest_id: str
    objective: PolicyObjective
    fallback_action: str = "no_email"
    uncertainty_threshold_candidates: tuple[float, ...] = (0.0, 0.05, 0.1)
    capacity_fraction: float | None = None
    propensity_source: str = "design_equal_thirds"
    seed: int = 1729
    track: Track = Track.HILLSTROM_POLICY
    execution_profile: ExecutionProfile = ExecutionProfile.LOCAL_DEVELOPMENT
    estimator_backend: EstimatorBackend = EstimatorBackend.SKLEARN_POLICY
    evidence_status: EvidenceStatus = EvidenceStatus.DEVELOPMENT_ONLY
    specification_version: str = "hillstrom_policy_v5"

    @property
    def specification_id(self) -> str:
        return content_id("policy_spec", self)


@dataclass(frozen=True)
class FrozenPolicyArtifact:
    policy_name: str
    policy_class: str
    dataset_hash: str
    split_manifest_id: str
    preprocessing: PreprocessingArtifact
    actions: tuple[str, ...]
    coefficients: tuple[tuple[float, ...], ...]
    intercepts: tuple[float, ...]
    objective: PolicyObjective
    fallback_action: str
    uncertainty_method: str
    uncertainty_threshold: float
    capacity_fraction: float | None
    selection_split: str
    refit_split: str
    created_without_test_outcomes: bool
    track: Track
    execution_profile: ExecutionProfile
    estimator_backend: EstimatorBackend
    evidence_status: EvidenceStatus
    seed: int

    @property
    def policy_id(self) -> str:
        return content_id("policy", self)
