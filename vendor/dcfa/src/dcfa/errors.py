"""Typed failures used by deterministic tools and the agent state machine."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_SPECIFICATION = "INVALID_SPECIFICATION"
    MISSING_CAUSAL_ROLE = "MISSING_CAUSAL_ROLE"
    ROLE_CONFLICT = "ROLE_CONFLICT"
    UNSUPPORTED_BASELINE_COVARIATES = "UNSUPPORTED_BASELINE_COVARIATES"
    UNSUPPORTED_TREATMENT = "UNSUPPORTED_TREATMENT"
    UNSUPPORTED_BACKEND_PROFILE = "UNSUPPORTED_BACKEND_PROFILE"
    INVALID_DATA = "INVALID_DATA"
    OUTSIDE_SUPPORT = "OUTSIDE_SUPPORT"
    MANAGED_QUOTA_EXHAUSTED = "MANAGED_QUOTA_EXHAUSTED"
    MANAGED_RATE_LIMITED = "MANAGED_RATE_LIMITED"
    MANAGED_SERVICE_FAILED = "MANAGED_SERVICE_FAILED"
    V2_UNAVAILABLE = "V2_UNAVAILABLE"
    V2_EXECUTION_FAILED = "V2_EXECUTION_FAILED"
    BACKEND_IMPORT_FAILED = "BACKEND_IMPORT_FAILED"
    BACKEND_LOAD_FAILED = "BACKEND_LOAD_FAILED"
    BACKEND_FIT_FAILED = "BACKEND_FIT_FAILED"
    BACKEND_PREDICT_FAILED = "BACKEND_PREDICT_FAILED"
    LLM_IMPORT_FAILED = "LLM_IMPORT_FAILED"
    LLM_API_FAILED = "LLM_API_FAILED"
    LLM_OUTPUT_INVALID = "LLM_OUTPUT_INVALID"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    STALE_ID = "STALE_ID"
    RELEASE_GATE_FAILED = "RELEASE_GATE_FAILED"
    CACHE_MISMATCH = "CACHE_MISMATCH"
    DATA_ACCESS_BLOCKED = "DATA_ACCESS_BLOCKED"
    SPLIT_LEAKAGE = "SPLIT_LEAKAGE"
    POLICY_NOT_FROZEN = "POLICY_NOT_FROZEN"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"
    OUTPUT_PATH_EXISTS = "OUTPUT_PATH_EXISTS"


class DCFAError(Exception):
    """A serializable, fail-closed error with stable routing semantics."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        stage: str,
        recoverable: bool = False,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.recoverable = bool(recoverable)
        self.context = dict(context or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "stage": self.stage,
            "recoverable": self.recoverable,
            "context": self.context,
        }


class BackendError(DCFAError):
    """A backend boundary failure that must never cause an implicit model switch."""
