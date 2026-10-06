"""Frozen development-only local TabPFN v2 deployment profile."""

from __future__ import annotations

from pathlib import Path

from dcfa.constants import EvidenceStatus, ExecutionProfile
from dcfa.errors import DCFAError, ErrorCode
from dcfa.schemas import AnalysisSpecification
from dcfa.tabcf_iv.backend import TabPFNBackend

LOCAL_TABPFN_V2_PROTOCOL_VERSION = "local_tabpfn_v2_zerogpu_v1"
LOCAL_TABPFN_V2_MODEL_VERSION = "v2"
LOCAL_TABPFN_V2_MODEL_REPO = "Prior-Labs/TabPFN-v2-reg"
LOCAL_TABPFN_V2_MODEL_REVISION = "4972a65a1b30806315c6f92499959ffbfc69a673"
LOCAL_TABPFN_V2_MODEL_FILENAME = "tabpfn-v2-regressor-v2_default.ckpt"
LOCAL_TABPFN_V2_MODEL_HASH = (
    "sha256:2ab5a07d5c41dfe6db9aa7ae106fc6de898326c2765be66505a07e2868c10736"
)
LOCAL_TABPFN_V2_N_ESTIMATORS = 1
LOCAL_TABPFN_V2_DEVICE = "cuda"

LOCAL_TABPFN_V2_BACKEND_PARAMETERS = (
    ("access_mode", "local_model"),
    ("deployment_protocol_version", LOCAL_TABPFN_V2_PROTOCOL_VERSION),
    ("device", LOCAL_TABPFN_V2_DEVICE),
    ("fallback", "none"),
    ("model_artifact_hash", LOCAL_TABPFN_V2_MODEL_HASH),
    ("model_filename", LOCAL_TABPFN_V2_MODEL_FILENAME),
    ("model_repo", LOCAL_TABPFN_V2_MODEL_REPO),
    ("model_revision", LOCAL_TABPFN_V2_MODEL_REVISION),
    ("model_version", LOCAL_TABPFN_V2_MODEL_VERSION),
    ("n_estimators", str(LOCAL_TABPFN_V2_N_ESTIMATORS)),
)


def make_local_tabpfn_v2_backend(
    specification: AnalysisSpecification,
    *,
    model_path: Path,
) -> TabPFNBackend:
    """Build the exact local v2 backend after specification validation."""
    if tuple(specification.backend_parameters) != LOCAL_TABPFN_V2_BACKEND_PARAMETERS:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Local TabPFN v2 requires the exact frozen deployment parameters.",
            stage="local_tabpfn_v2.specification",
        )
    if (
        specification.execution_profile is not ExecutionProfile.LOCAL_DEVELOPMENT
        or specification.evidence_status is not EvidenceStatus.DEVELOPMENT_ONLY
    ):
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "Local TabPFN v2 is restricted to local_development/development_only.",
            stage="local_tabpfn_v2.specification",
        )
    return TabPFNBackend(
        seed=specification.seed,
        execution_profile=specification.execution_profile,
        model_path=str(model_path),
        model_artifact_hash=LOCAL_TABPFN_V2_MODEL_HASH,
        model_version=LOCAL_TABPFN_V2_MODEL_VERSION,
        model_repo=LOCAL_TABPFN_V2_MODEL_REPO,
        model_revision=LOCAL_TABPFN_V2_MODEL_REVISION,
        model_filename=LOCAL_TABPFN_V2_MODEL_FILENAME,
        n_estimators=LOCAL_TABPFN_V2_N_ESTIMATORS,
        device=LOCAL_TABPFN_V2_DEVICE,
    )
