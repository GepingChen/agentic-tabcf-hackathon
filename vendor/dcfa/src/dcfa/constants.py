"""Repository-wide values that define the v1 execution and evidence boundary."""

from __future__ import annotations

from enum import StrEnum


class Track(StrEnum):
    TABCF_IV = "tabcf_iv"
    HILLSTROM_POLICY = "hillstrom_policy"
    AGENT_BENCHMARK = "agent_benchmark"


class ExecutionProfile(StrEnum):
    LOCAL_DEVELOPMENT = "local_development"
    LOCKED_EVALUATION = "locked_evaluation"
    TEST = "test"


class EstimatorBackend(StrEnum):
    SKLEARN_QUANTILE_FALLBACK = "sklearn_quantile_fallback"
    TABPFN = "tabpfn"
    SKLEARN_POLICY = "sklearn_policy"
    MOCK = "mock"


class EvidenceStatus(StrEnum):
    DEVELOPMENT_ONLY = "development_only"
    ELIGIBLE_FOR_RELEASE = "eligible_for_release"
    TEST_ONLY = "test_only"


class SupportStatus(StrEnum):
    SUPPORTED = "supported"
    WEAK_SUPPORT = "weak_support"
    UNSUPPORTED = "unsupported"


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


LOCAL_FALLBACK_MARKERS = {
    "execution_profile": ExecutionProfile.LOCAL_DEVELOPMENT.value,
    "estimator_backend": EstimatorBackend.SKLEARN_QUANTILE_FALLBACK.value,
    "evidence_status": EvidenceStatus.DEVELOPMENT_ONLY.value,
}
