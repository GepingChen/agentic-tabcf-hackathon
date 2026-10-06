"""Single orchestrator with typed routing, one retry, caching, and evidence gates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from dcfa.agent.compiler import CompilationRequest, SpecificationCompiler
from dcfa.agent.state import AgentState, StateEvent, StateMachine
from dcfa.errors import DCFAError, ErrorCode
from dcfa.evidence import validate_bundle_evidence
from dcfa.schemas import (
    AnalysisSpecification,
    DatasetManifest,
    QueryResult,
    WarningRecord,
)
from dcfa.tabcf_iv.pipeline import AnalysisRun, TabCFAnalysisEngine
from dcfa.tabcf_iv.validation import validate_tabcf_specification


class AnalysisTool(Protocol):
    def analyze(
        self,
        data: Mapping[str, np.ndarray],
        specification: AnalysisSpecification,
        dataset_manifest: DatasetManifest,
        *,
        output_dir: Any = None,
    ) -> AnalysisRun: ...

    def follow_up(
        self,
        specification: AnalysisSpecification,
        query_id: str,
    ) -> QueryResult: ...


@dataclass(frozen=True)
class AgentResponse:
    status: str
    final_state: AgentState
    specification_id: str | None
    result_bundle_id: str | None
    queries: tuple[QueryResult, ...]
    warnings: tuple[WarningRecord, ...]
    clarification_questions: tuple[str, ...]
    error: dict[str, Any] | None
    tool_calls: int
    retry_count: int
    state_events: tuple[StateEvent, ...]


class CausalAgentRuntime:
    def __init__(
        self,
        *,
        analysis_tool: AnalysisTool | None = None,
        compiler: SpecificationCompiler | None = None,
    ) -> None:
        self.analysis_tool = analysis_tool or TabCFAnalysisEngine()
        self.compiler = compiler or SpecificationCompiler()

    def execute(
        self,
        request: CompilationRequest,
        data: Mapping[str, np.ndarray],
        dataset_manifest: DatasetManifest,
    ) -> AgentResponse:
        machine = StateMachine()
        machine.transition(AgentState.COMPILING, reason="compile_typed_request")
        try:
            compiled = self.compiler.compile(request)
        except DCFAError as exc:
            machine.transition(AgentState.BLOCKED, reason=exc.code.value)
            return self._error_response(machine, exc, tool_calls=0, retry_count=0)
        if compiled.requires_clarification:
            machine.transition(
                AgentState.CLARIFICATION_REQUIRED,
                reason="required_fields_or_objective_missing",
            )
            return AgentResponse(
                status="clarification_required",
                final_state=machine.state,
                specification_id=None,
                result_bundle_id=None,
                queries=(),
                warnings=(),
                clarification_questions=compiled.clarification_questions,
                error=None,
                tool_calls=0,
                retry_count=0,
                state_events=machine.events(),
            )

        specification = compiled.specification
        assert specification is not None
        if not specification.confirmed_by_user:
            machine.transition(
                AgentState.APPROVAL_REQUIRED,
                reason="immutable_specification_requires_user_confirmation",
            )
            return AgentResponse(
                status="approval_required",
                final_state=machine.state,
                specification_id=specification.specification_id,
                result_bundle_id=None,
                queries=(),
                warnings=(),
                clarification_questions=(
                    "Confirm the immutable Y/X/Z roles, estimand, intervention grid, and "
                    "development-only backend before execution.",
                ),
                error=None,
                tool_calls=0,
                retry_count=0,
                state_events=machine.events(),
            )
        try:
            validate_tabcf_specification(specification)
        except DCFAError as exc:
            machine.transition(AgentState.BLOCKED, reason=exc.code.value)
            return self._error_response(
                machine,
                exc,
                tool_calls=0,
                retry_count=0,
                specification_id=specification.specification_id,
            )
        machine.transition(
            AgentState.SPECIFICATION_VALIDATED,
            reason="immutable_specification_validated",
        )

        tool_calls = 0
        retry_count = 0
        run: AnalysisRun | None = None
        while run is None:
            machine.transition(AgentState.EXECUTING, reason="call_deterministic_analysis_tool")
            tool_calls += 1
            try:
                run = self.analysis_tool.analyze(data, specification, dataset_manifest)
            except DCFAError as exc:
                if exc.recoverable and retry_count == 0:
                    retry_count = 1
                    machine.transition(AgentState.RETRYING, reason=exc.code.value)
                    continue
                machine.transition(AgentState.BLOCKED, reason=exc.code.value)
                return self._error_response(
                    machine,
                    exc,
                    tool_calls=tool_calls,
                    retry_count=retry_count,
                    specification_id=specification.specification_id,
                )

        machine.transition(AgentState.VALIDATING_EVIDENCE, reason="validate_result_bundle")
        try:
            if run.bundle.dataset_hash != specification.dataset_hash:
                raise DCFAError(
                    ErrorCode.HASH_MISMATCH,
                    "The tool result dataset hash does not match the compiled specification.",
                    stage="agent.evidence_validation",
                )
            if run.bundle.specification_id != specification.specification_id:
                raise DCFAError(
                    ErrorCode.EVIDENCE_MISMATCH,
                    "The tool result does not match the compiled specification.",
                    stage="agent.evidence_validation",
                )
            validate_bundle_evidence(run.bundle, run.ledger)
        except DCFAError as exc:
            machine.transition(AgentState.BLOCKED, reason=exc.code.value)
            return self._error_response(
                machine,
                exc,
                tool_calls=tool_calls,
                retry_count=retry_count,
                specification_id=specification.specification_id,
            )
        machine.transition(AgentState.COMPLETED, reason="validated_evidence_only_answer")
        return AgentResponse(
            status="completed",
            final_state=machine.state,
            specification_id=specification.specification_id,
            result_bundle_id=run.bundle.result_bundle_id,
            queries=run.bundle.queries,
            warnings=run.bundle.warnings,
            clarification_questions=(),
            error=None,
            tool_calls=tool_calls,
            retry_count=retry_count,
            state_events=machine.events(),
        )

    def follow_up(
        self,
        specification: AnalysisSpecification,
        query_id: str,
    ) -> AgentResponse:
        machine = StateMachine()
        machine.transition(AgentState.CACHE_LOOKUP, reason="ordinary_follow_up")
        try:
            query = self.analysis_tool.follow_up(specification, query_id)
        except DCFAError as exc:
            machine.transition(AgentState.BLOCKED, reason=exc.code.value)
            return self._error_response(
                machine,
                exc,
                tool_calls=1,
                retry_count=0,
                specification_id=specification.specification_id,
            )
        machine.transition(AgentState.COMPLETED, reason="cached_query_resolved_without_refit")
        return AgentResponse(
            status="completed_from_cache",
            final_state=machine.state,
            specification_id=specification.specification_id,
            result_bundle_id=None,
            queries=(query,),
            warnings=query.warnings,
            clarification_questions=(),
            error=None,
            tool_calls=1,
            retry_count=0,
            state_events=machine.events(),
        )

    @staticmethod
    def _error_response(
        machine: StateMachine,
        error: DCFAError,
        *,
        tool_calls: int,
        retry_count: int,
        specification_id: str | None = None,
    ) -> AgentResponse:
        return AgentResponse(
            status="blocked",
            final_state=machine.state,
            specification_id=specification_id,
            result_bundle_id=None,
            queries=(),
            warnings=(),
            clarification_questions=(),
            error=error.to_dict(),
            tool_calls=tool_calls,
            retry_count=retry_count,
            state_events=machine.events(),
        )


def stale_cached_follow_up_error(query_id: str) -> DCFAError:
    """Stable fixture helper for recorded benchmark tools."""
    return DCFAError(
        ErrorCode.STALE_ID,
        f"Cached query ID {query_id} is stale.",
        stage="cache.follow_up",
    )
