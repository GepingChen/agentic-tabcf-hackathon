"""Auditable state graph for the local single-agent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dcfa.canonical import content_id


class AgentState(StrEnum):
    RECEIVED = "received"
    COMPILING = "compiling"
    CLARIFICATION_REQUIRED = "clarification_required"
    APPROVAL_REQUIRED = "approval_required"
    SPECIFICATION_VALIDATED = "specification_validated"
    EXECUTING = "executing"
    RETRYING = "retrying"
    VALIDATING_EVIDENCE = "validating_evidence"
    CACHE_LOOKUP = "cache_lookup"
    COMPLETED = "completed"
    BLOCKED = "blocked"


ALLOWED_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.RECEIVED: frozenset({AgentState.COMPILING, AgentState.CACHE_LOOKUP}),
    AgentState.COMPILING: frozenset(
        {
            AgentState.CLARIFICATION_REQUIRED,
            AgentState.APPROVAL_REQUIRED,
            AgentState.SPECIFICATION_VALIDATED,
            AgentState.BLOCKED,
        }
    ),
    AgentState.SPECIFICATION_VALIDATED: frozenset({AgentState.EXECUTING, AgentState.BLOCKED}),
    AgentState.EXECUTING: frozenset(
        {AgentState.RETRYING, AgentState.VALIDATING_EVIDENCE, AgentState.BLOCKED}
    ),
    AgentState.RETRYING: frozenset({AgentState.EXECUTING, AgentState.BLOCKED}),
    AgentState.VALIDATING_EVIDENCE: frozenset({AgentState.COMPLETED, AgentState.BLOCKED}),
    AgentState.CACHE_LOOKUP: frozenset({AgentState.COMPLETED, AgentState.BLOCKED}),
    AgentState.CLARIFICATION_REQUIRED: frozenset(),
    AgentState.APPROVAL_REQUIRED: frozenset(),
    AgentState.COMPLETED: frozenset(),
    AgentState.BLOCKED: frozenset(),
}


@dataclass(frozen=True)
class StateEvent:
    event_id: str
    sequence: int
    previous_state: AgentState | None
    state: AgentState
    reason: str


class StateMachine:
    def __init__(self) -> None:
        self.state = AgentState.RECEIVED
        initial = {
            "sequence": 0,
            "previous_state": None,
            "state": self.state,
            "reason": "request_received",
        }
        self._events = [StateEvent(event_id=content_id("state", initial), **initial)]

    def transition(self, target: AgentState, *, reason: str) -> StateEvent:
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise RuntimeError(f"Invalid agent transition: {self.state.value} -> {target.value}.")
        previous = self.state
        self.state = target
        payload = {
            "sequence": len(self._events),
            "previous_state": previous,
            "state": target,
            "reason": reason,
        }
        event = StateEvent(event_id=content_id("state", payload), **payload)
        self._events.append(event)
        return event

    def events(self) -> tuple[StateEvent, ...]:
        return tuple(self._events)
