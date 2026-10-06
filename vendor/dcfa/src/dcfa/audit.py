"""Append-only typed audit events for deterministic local runs."""

from __future__ import annotations

from dataclasses import dataclass

from dcfa.canonical import content_id
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    sequence: int
    event_type: str
    stage: str
    status: str
    specification_id: str
    run_id: str | None
    track: Track
    execution_profile: ExecutionProfile
    estimator_backend: EstimatorBackend
    evidence_status: EvidenceStatus
    details: tuple[tuple[str, str], ...]


class AuditTrail:
    def __init__(
        self,
        *,
        specification_id: str,
        track: Track,
        execution_profile: ExecutionProfile,
        estimator_backend: EstimatorBackend,
        evidence_status: EvidenceStatus,
    ) -> None:
        self.specification_id = specification_id
        self.track = track
        self.execution_profile = execution_profile
        self.estimator_backend = estimator_backend
        self.evidence_status = evidence_status
        self._events: list[AuditEvent] = []

    def append(
        self,
        *,
        event_type: str,
        stage: str,
        status: str,
        run_id: str | None = None,
        details: tuple[tuple[str, str], ...] = (),
    ) -> AuditEvent:
        payload = {
            "sequence": len(self._events),
            "event_type": event_type,
            "stage": stage,
            "status": status,
            "specification_id": self.specification_id,
            "run_id": run_id,
            "track": self.track,
            "execution_profile": self.execution_profile,
            "estimator_backend": self.estimator_backend,
            "evidence_status": self.evidence_status,
            "details": details,
        }
        event = AuditEvent(event_id=content_id("audit", payload), **payload)
        self._events.append(event)
        return event

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)
