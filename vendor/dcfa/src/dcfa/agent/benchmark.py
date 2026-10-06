"""Recorded-fixture Track A harness with identical tools for both systems."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from dcfa.agent.compiler import CompilationRequest, SpecificationCompiler
from dcfa.agent.runtime import AgentResponse, CausalAgentRuntime
from dcfa.agent.state import AgentState
from dcfa.audit import AuditTrail
from dcfa.canonical import content_id, sha256_digest
from dcfa.constants import (
    EstimatorBackend,
    EvidenceStatus,
    ExecutionProfile,
    SupportStatus,
    Track,
    WarningSeverity,
)
from dcfa.errors import DCFAError, ErrorCode
from dcfa.evidence import EvidenceLedger, build_evidence_record, validate_bundle_evidence
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.schemas import (
    AnalysisSpecification,
    DatasetManifest,
    DiagnosticBundle,
    QueryResult,
    ResultBundle,
    RunManifest,
    SupportAssessment,
    WarningRecord,
)
from dcfa.tabcf_iv.pipeline import AnalysisRun
from dcfa.tabcf_iv.validation import validate_tabcf_specification

RECORDED_FIXTURE_VALUE = 1.25


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    family: str
    mode: str
    request: dict[str, Any]
    fixture_behavior: str
    expected_final_state: str
    expected_error_code: str | None
    expected_max_analyze_calls: int
    required_warning_code: str | None


@dataclass(frozen=True)
class BenchmarkTrace:
    case_id: str
    run_index: int
    family: str
    fixture_behavior: str
    system: str
    expected_final_state: str
    expected_max_analyze_calls: int
    final_state: str
    status: str
    error_code: str | None
    tool_calls: int
    analyze_calls: int
    follow_up_calls: int
    retry_count: int
    warning_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    values: tuple[float, ...]
    numerical_fidelity: bool
    valid_completion: bool
    grader_failures: tuple[str, ...]


def load_benchmark_cases(path: Path) -> tuple[BenchmarkCase, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != "track_a_cases_v1":
        raise ValueError("Unsupported benchmark case version.")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) < 24:
        raise ValueError("Track A MVP requires at least 24 benchmark cases.")
    cases = tuple(BenchmarkCase(**item) for item in raw_cases)
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Benchmark case IDs must be unique.")
    return cases


def _compilation_request(case: BenchmarkCase, dataset_hash: str) -> CompilationRequest:
    request = case.request
    return CompilationRequest(
        dataset_hash=dataset_hash,
        outcome=request.get("outcome"),
        treatment=request.get("treatment"),
        instrument=request.get("instrument"),
        objective=request.get("objective"),
        intervention_grid=tuple(
            float(value) for value in request.get("intervention_grid", [-1.0, 0.0, 1.0])
        ),
        x=None if request.get("x") is None else float(request["x"]),
        comparison_x=(
            None if request.get("comparison_x") is None else float(request["comparison_x"])
        ),
        level=None if request.get("level") is None else float(request["level"]),
        threshold=(None if request.get("threshold") is None else float(request["threshold"])),
        baseline_covariates=tuple(request.get("baseline_covariates", [])),
        treatment_type=str(request.get("treatment_type", "continuous")),
        units=str(request.get("units", "Y_units")),
        seed=401,
    )


def _claim_type(kind: str) -> str:
    return {
        "mean": "interventional_mean",
        "quantile": "interventional_quantile",
        "risk": "threshold_risk",
        "mean_contrast": "mean_contrast_x_minus_comparison_x",
        "quantile_contrast": "quantile_contrast_x_minus_comparison_x",
        "risk_contrast": "risk_contrast_x_minus_comparison_x",
    }[kind]


class RecordedAnalysisTool:
    """Deterministic fixture tool; it never fits or imports a statistical backend."""

    def __init__(
        self,
        *,
        behavior: str,
        fixture_value: float = RECORDED_FIXTURE_VALUE,
    ) -> None:
        self.behavior = behavior
        self.fixture_value = float(fixture_value)
        self.analyze_calls = 0
        self.follow_up_calls = 0
        self._last_run: AnalysisRun | None = None

    def _build_run(self, specification: AnalysisSpecification) -> AnalysisRun:
        warnings: tuple[WarningRecord, ...] = ()
        if self.behavior == "weak_warning":
            warnings = (
                WarningRecord(
                    code="WEAK_FIRST_STAGE_EMPIRICAL_WARNING",
                    message=(
                        "Recorded empirical relevance warning; it does not prove invalidity "
                        "or establish identification."
                    ),
                    severity=WarningSeverity.WARNING,
                    source="recorded_fixture",
                ),
            )
        run_id = content_id(
            "run",
            {"specification_id": specification.specification_id, "fixture": self.behavior},
        )
        source_hash = sha256_digest(
            {"case_fixture": self.behavior, "specification_id": specification.specification_id}
        )
        bundle_payload = {
            "run_id": run_id,
            "specification_id": specification.specification_id,
            "dataset_hash": specification.dataset_hash,
            "fixture": self.behavior,
            "value": self.fixture_value,
        }
        bundle_id = content_id("bundle", bundle_payload)
        query_spec = specification.queries[0]
        evidence = build_evidence_record(
            track=Track.TABCF_IV,
            evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
            estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
            execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
            run_id=run_id,
            dataset_hash=specification.dataset_hash,
            specification_id=specification.specification_id,
            result_bundle_id=bundle_id,
            claim_type=_claim_type(query_spec.kind),
            value_raw=self.fixture_value,
            value_display=format(self.fixture_value, ".6g"),
            units=query_spec.units,
            support_status=SupportStatus.SUPPORTED,
            warnings=warnings,
            source_artifact="recorded_fixture.json",
            source_artifact_hash=source_hash,
        )
        query = QueryResult(
            query_id=query_spec.query_id,
            claim_type=evidence.claim_type,
            value_raw=evidence.value_raw,
            value_display=evidence.value_display,
            units=evidence.units,
            support_status=evidence.support_status,
            warnings=evidence.warnings,
            evidence_id=evidence.evidence_id,
        )
        support = tuple(
            SupportAssessment(
                x=float(value),
                status=SupportStatus.SUPPORTED,
                coverage_score=1.0,
                recommended_interval=(
                    float(specification.intervention_grid[0]),
                    float(specification.intervention_grid[-1]),
                ),
                strict_interval=(
                    float(specification.intervention_grid[0]),
                    float(specification.intervention_grid[-1]),
                ),
                reason="Recorded supported fixture.",
            )
            for value in specification.intervention_grid
        )
        n_x = len(specification.intervention_grid)
        quantile_levels = specification.quantile_levels
        risk_thresholds = specification.risk_thresholds
        bundle = ResultBundle(
            result_bundle_id=bundle_id,
            run_id=run_id,
            specification_id=specification.specification_id,
            dataset_hash=specification.dataset_hash,
            track=Track.TABCF_IV,
            execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
            estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
            evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
            x_grid=specification.intervention_grid,
            y_grid=(0.0, 1.0),
            interventional_cdf=tuple((0.0, 1.0) for _ in range(n_x)),
            interventional_mean=tuple(self.fixture_value for _ in range(n_x)),
            quantile_levels=quantile_levels,
            interventional_quantiles=tuple(
                tuple(self.fixture_value for _ in quantile_levels) for _ in range(n_x)
            ),
            risk_thresholds=risk_thresholds,
            interventional_risks=tuple(
                tuple(self.fixture_value for _ in risk_thresholds) for _ in range(n_x)
            ),
            diagnostics=DiagnosticBundle(
                first_stage_f=20.0,
                first_stage_r2=0.5,
                control_rank_cvm=0.01,
                control_rank_mean=0.5,
                residual_dependence_score=0.05,
            ),
            support=support,
            warnings=warnings,
            assumptions=("Recorded Track A orchestration fixture; not estimator evidence.",),
            queries=(query,),
            source_artifact="recorded_fixture.json",
            source_artifact_hash=source_hash,
        )
        if self.behavior == "evidence_mismatch":
            bundle = replace(bundle, queries=(replace(query, value_raw=query.value_raw + 1.0),))
        if self.behavior == "hash_mismatch":
            bundle = replace(bundle, dataset_hash="sha256:injected_mismatch")
        ledger = EvidenceLedger((evidence,))
        audit = AuditTrail(
            specification_id=specification.specification_id,
            track=Track.AGENT_BENCHMARK,
            execution_profile=ExecutionProfile.TEST,
            estimator_backend=EstimatorBackend.MOCK,
            evidence_status=EvidenceStatus.TEST_ONLY,
        )
        audit.append(
            event_type="recorded_fixture_returned",
            stage="track_a.fixture",
            status="completed",
            run_id=run_id,
        )
        manifest = RunManifest(
            run_id=run_id,
            specification_id=specification.specification_id,
            dataset_hash=specification.dataset_hash,
            backend_manifest_id="recorded_fixture",
            track=Track.AGENT_BENCHMARK,
            execution_profile=ExecutionProfile.TEST,
            estimator_backend=EstimatorBackend.MOCK,
            evidence_status=EvidenceStatus.TEST_ONLY,
            seed=401,
        )
        return AnalysisRun(bundle, ledger, audit, manifest, (), 0)

    def analyze(
        self,
        data: dict[str, np.ndarray],
        specification: AnalysisSpecification,
        dataset_manifest: DatasetManifest,
        *,
        output_dir: Any = None,
    ) -> AnalysisRun:
        del data, dataset_manifest, output_dir
        self.analyze_calls += 1
        if self.behavior == "outside_support":
            raise DCFAError(
                ErrorCode.OUTSIDE_SUPPORT,
                "Recorded outside-support block.",
                stage="fixture.support",
            )
        if self.behavior in {"recoverable_once", "recoverable_always"}:
            if self.behavior == "recoverable_always" or self.analyze_calls == 1:
                raise DCFAError(
                    ErrorCode.BACKEND_PREDICT_FAILED,
                    "Recorded recoverable backend failure.",
                    stage="fixture.backend",
                    recoverable=True,
                )
        self._last_run = self._build_run(specification)
        return self._last_run

    def follow_up(
        self,
        specification: AnalysisSpecification,
        query_id: str,
    ) -> QueryResult:
        self.follow_up_calls += 1
        if self.behavior == "stale_id":
            raise DCFAError(
                ErrorCode.STALE_ID,
                "Recorded stale query ID.",
                stage="fixture.cache",
            )
        if self._last_run is None:
            self._last_run = self._build_run(specification)
        query = self._last_run.bundle.queries[0]
        if query_id not in {"cached_query", query.query_id}:
            raise DCFAError(
                ErrorCode.STALE_ID,
                "Recorded query ID not found.",
                stage="fixture.cache",
            )
        return query


class FixedWorkflowRunner:
    """Same compiler/tool/evidence validator in a fixed chain with no dynamic retry."""

    def __init__(self, tool: RecordedAnalysisTool) -> None:
        self.tool = tool
        self.compiler = SpecificationCompiler()

    def run(
        self,
        case: BenchmarkCase,
        request: CompilationRequest,
        data: dict[str, np.ndarray],
        manifest: DatasetManifest,
    ) -> AgentResponse:
        if case.mode == "follow_up":
            compiled = self.compiler.compile(request)
            if compiled.specification is None:
                return _simple_blocked(ErrorCode.INVALID_SPECIFICATION)
            # A fixed chain unnecessarily recomputes before answering the follow-up.
            try:
                run = self.tool.analyze(data, compiled.specification, manifest)
                validate_bundle_evidence(run.bundle, run.ledger)
            except DCFAError as exc:
                return _simple_blocked(exc.code, tool_calls=1)
            return _simple_completed(run.bundle.queries, run.bundle.warnings, tool_calls=1)
        try:
            compiled = self.compiler.compile(request)
            if compiled.requires_clarification or compiled.specification is None:
                return _simple_blocked(ErrorCode.INVALID_SPECIFICATION)
            validate_tabcf_specification(compiled.specification)
            run = self.tool.analyze(data, compiled.specification, manifest)
            validate_bundle_evidence(run.bundle, run.ledger)
        except DCFAError as exc:
            return _simple_blocked(exc.code, tool_calls=self.tool.analyze_calls)
        return _simple_completed(
            run.bundle.queries,
            run.bundle.warnings,
            tool_calls=self.tool.analyze_calls,
        )


def _simple_blocked(code: ErrorCode, *, tool_calls: int = 0) -> AgentResponse:
    return AgentResponse(
        status="blocked",
        final_state=AgentState.BLOCKED,
        specification_id=None,
        result_bundle_id=None,
        queries=(),
        warnings=(),
        clarification_questions=(),
        error={"code": code.value},
        tool_calls=tool_calls,
        retry_count=0,
        state_events=(),
    )


def _simple_completed(
    queries: tuple[QueryResult, ...],
    warnings: tuple[WarningRecord, ...],
    *,
    tool_calls: int,
) -> AgentResponse:
    return AgentResponse(
        status="completed",
        final_state=AgentState.COMPLETED,
        specification_id=None,
        result_bundle_id=None,
        queries=queries,
        warnings=warnings,
        clarification_questions=(),
        error=None,
        tool_calls=tool_calls,
        retry_count=0,
        state_events=(),
    )


def _trace_grade_outcome(
    case: BenchmarkCase,
    *,
    final_state: str,
    error_code: str | None,
    analyze_calls: int,
    warning_codes: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    values: tuple[float, ...],
    fixture_value: float,
) -> tuple[bool, tuple[str, ...]]:
    """Recompute the deterministic gold-aware grade for one recorded trace."""
    failures: list[str] = []
    if final_state != case.expected_final_state:
        failures.append("wrong_final_state")
    if case.expected_error_code is not None and error_code != case.expected_error_code:
        failures.append("wrong_error_code")
    if analyze_calls > case.expected_max_analyze_calls:
        failures.append("unnecessary_refit_or_tool_call")
    if case.required_warning_code is not None and case.required_warning_code not in warning_codes:
        failures.append("warning_not_preserved")
    if final_state != AgentState.COMPLETED.value and values:
        failures.append("numerical_claim_after_block")
    if case.expected_final_state != AgentState.COMPLETED.value and values:
        failures.append("numerical_claim_when_gold_requires_no_answer")
    if final_state == AgentState.COMPLETED.value and any(not item for item in evidence_ids):
        failures.append("missing_evidence_id")
    numerical_fidelity = case.expected_final_state != AgentState.COMPLETED.value or values == (
        fixture_value,
    )
    if not numerical_fidelity:
        failures.append("numerical_fidelity_failure")
    return numerical_fidelity, tuple(failures)


def _grade(
    case: BenchmarkCase,
    system: str,
    response: AgentResponse,
    tool: RecordedAnalysisTool,
    *,
    run_index: int,
) -> BenchmarkTrace:
    error_code = None if response.error is None else str(response.error.get("code"))
    warning_codes = tuple(warning.code for warning in response.warnings)
    evidence_ids = tuple(query.evidence_id for query in response.queries)
    values = tuple(query.value_raw for query in response.queries)
    numerical_fidelity, grader_failures = _trace_grade_outcome(
        case,
        final_state=response.final_state.value,
        error_code=error_code,
        analyze_calls=tool.analyze_calls,
        warning_codes=warning_codes,
        evidence_ids=evidence_ids,
        values=values,
        fixture_value=tool.fixture_value,
    )
    return BenchmarkTrace(
        case_id=case.case_id,
        run_index=run_index,
        family=case.family,
        fixture_behavior=case.fixture_behavior,
        system=system,
        expected_final_state=case.expected_final_state,
        expected_max_analyze_calls=case.expected_max_analyze_calls,
        final_state=response.final_state.value,
        status=response.status,
        error_code=error_code,
        tool_calls=response.tool_calls,
        analyze_calls=tool.analyze_calls,
        follow_up_calls=tool.follow_up_calls,
        retry_count=response.retry_count,
        warning_codes=warning_codes,
        evidence_ids=evidence_ids,
        values=values,
        numerical_fidelity=numerical_fidelity,
        valid_completion=not grader_failures,
        grader_failures=grader_failures,
    )


def run_recorded_benchmark(
    cases: tuple[BenchmarkCase, ...],
    *,
    repetitions: int = 1,
) -> tuple[BenchmarkTrace, ...]:
    if repetitions <= 0:
        raise ValueError("Benchmark repetitions must be positive.")
    dataset_hash = "sha256:" + "4" * 64
    manifest = DatasetManifest(
        dataset_id="dataset_track_a_recorded",
        dataset_hash=dataset_hash,
        source="recorded_track_a_fixture",
        source_kind="recorded_fixture",
        row_count=100,
        columns=("Z", "X", "Y"),
        generation_seed=401,
        dgp_label=None,
        dgp_mapping_status="not_applicable",
        license_note="Synthetic recorded fixture.",
        track=Track.TABCF_IV,
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
    )
    dummy_data = {
        "Z": np.linspace(-1.0, 1.0, 100),
        "X": np.linspace(-1.0, 1.0, 100),
        "Y": np.linspace(-1.0, 1.0, 100),
    }
    traces: list[BenchmarkTrace] = []
    for run_index in range(repetitions):
        for case in cases:
            request = _compilation_request(case, dataset_hash)
            full_tool = RecordedAnalysisTool(behavior=case.fixture_behavior)
            fixed_tool = RecordedAnalysisTool(behavior=case.fixture_behavior)
            compiler = SpecificationCompiler()
            if case.mode == "follow_up":
                compiled = compiler.compile(request)
                if compiled.specification is None:
                    raise ValueError(
                        f"Follow-up case {case.case_id} must compile without clarification."
                    )
                full_response = CausalAgentRuntime(analysis_tool=full_tool).follow_up(
                    compiled.specification,
                    str(case.request.get("query_id", "cached_query")),
                )
            else:
                full_response = CausalAgentRuntime(analysis_tool=full_tool).execute(
                    request,
                    dummy_data,
                    manifest,
                )
            fixed_response = FixedWorkflowRunner(fixed_tool).run(
                case,
                request,
                dummy_data,
                manifest,
            )
            traces.append(
                _grade(
                    case,
                    "full_agent",
                    full_response,
                    full_tool,
                    run_index=run_index,
                )
            )
            traces.append(
                _grade(
                    case,
                    "fixed_workflow",
                    fixed_response,
                    fixed_tool,
                    run_index=run_index,
                )
            )
    return tuple(traces)


def _case_level_comparison(
    traces: tuple[BenchmarkTrace, ...],
    *,
    case_ids: tuple[str, ...],
    seed: int,
) -> dict[str, Any]:
    differences: list[float] = []
    for case_id in case_ids:
        rates = {
            system: float(
                np.mean(
                    [
                        trace.valid_completion
                        for trace in traces
                        if trace.case_id == case_id and trace.system == system
                    ]
                )
            )
            for system in ("fixed_workflow", "full_agent")
        }
        differences.append(rates["full_agent"] - rates["fixed_workflow"])
    values = np.asarray(differences, dtype=float)
    paired_difference = float(np.mean(values))
    paired_standard_error = (
        0.0 if len(values) == 1 else float(np.std(values, ddof=1) / np.sqrt(len(values)))
    )
    rng = np.random.default_rng(seed)
    bootstrap_means = np.mean(
        values[rng.integers(0, len(values), size=(10_000, len(values)))],
        axis=1,
    )
    bootstrap_lower, bootstrap_upper = np.quantile(bootstrap_means, (0.025, 0.975))
    return {
        "estimand": "full_agent_minus_fixed_workflow_valid_completion_rate",
        "case_count": len(case_ids),
        "paired_difference": paired_difference,
        "standard_error_across_cases": paired_standard_error,
        "normal_interval_lower": paired_difference - 1.96 * paired_standard_error,
        "normal_interval_upper": paired_difference + 1.96 * paired_standard_error,
        "case_bootstrap_interval_lower": float(bootstrap_lower),
        "case_bootstrap_interval_upper": float(bootstrap_upper),
        "case_bootstrap_resamples": 10_000,
        "case_bootstrap_seed": seed,
        "analysis_unit": "case",
        "repeated_runs_nested_within_case": True,
    }


def benchmark_summary(traces: tuple[BenchmarkTrace, ...]) -> dict[str, Any]:
    systems = sorted({trace.system for trace in traces})
    if systems != ["fixed_workflow", "full_agent"]:
        raise ValueError("Track A summary requires fixed_workflow and full_agent traces.")
    case_ids = tuple(sorted({trace.case_id for trace in traces}))
    clean_case_ids = tuple(
        case_id
        for case_id in case_ids
        if next(trace.family for trace in traces if trace.case_id == case_id) == "clean_supported"
    )
    complex_case_ids = tuple(case_id for case_id in case_ids if case_id not in clean_case_ids)
    primary_comparison = _case_level_comparison(
        traces,
        case_ids=complex_case_ids,
        seed=20260808,
    )
    overall_comparison = _case_level_comparison(
        traces,
        case_ids=case_ids,
        seed=20260809,
    )
    clean_comparison = _case_level_comparison(
        traces,
        case_ids=clean_case_ids,
        seed=20260810,
    )
    case_results: dict[str, dict[str, Any]] = {}
    for case_id in case_ids:
        case_results[case_id] = {}
        for system in systems:
            rows = tuple(
                trace for trace in traces if trace.case_id == case_id and trace.system == system
            )
            signatures = {
                (
                    row.final_state,
                    row.error_code,
                    row.valid_completion,
                    row.values,
                    row.grader_failures,
                )
                for row in rows
            }
            case_results[case_id][system] = {
                "mean_valid_completion": float(np.mean([row.valid_completion for row in rows])),
                "worst_run_valid_completion": bool(all(row.valid_completion for row in rows)),
                "between_run_disagreement": len(signatures) > 1,
            }
    return {
        "benchmark_id": content_id(
            "track_a_benchmark",
            {
                "protocol_version": "track_a_recorded_v4",
                "dcfa_source_tree_hash": dcfa_source_tree_hash(),
                "traces": traces,
            },
        ),
        "benchmark_protocol_version": "track_a_recorded_v4",
        "dcfa_source_tree_hash": dcfa_source_tree_hash(),
        "track": Track.AGENT_BENCHMARK.value,
        "execution_profile": ExecutionProfile.TEST.value,
        "estimator_backend": EstimatorBackend.MOCK.value,
        "evidence_status": EvidenceStatus.TEST_ONLY.value,
        "case_count": len(case_ids),
        "runs_per_case": max(
            sum(trace.case_id == case_id and trace.system == systems[0] for trace in traces)
            for case_id in {trace.case_id for trace in traces}
        ),
        "primary_case_level_comparison": {
            **primary_comparison,
            "population": "complex_cases_in_current_suite",
        },
        "overall_case_level_comparison": overall_comparison,
        "clean_case_noninferiority": {
            **clean_comparison,
            "margin": -0.05,
            "passes_case_bootstrap_lower_bound": (
                clean_comparison["case_bootstrap_interval_lower"] > -0.05
            ),
        },
        "families": {
            family: {
                "systems": {
                    system: float(
                        np.mean(
                            [
                                trace.valid_completion
                                for trace in traces
                                if trace.family == family and trace.system == system
                            ]
                        )
                    )
                    for system in systems
                },
                "case_level_comparison": _case_level_comparison(
                    traces,
                    case_ids=tuple(
                        case_id
                        for case_id in case_ids
                        if next(trace.family for trace in traces if trace.case_id == case_id)
                        == family
                    ),
                    seed=20260900 + sorted({trace.family for trace in traces}).index(family),
                ),
            }
            for family in sorted({trace.family for trace in traces})
        },
        "per_case": case_results,
        "systems": {
            system: {
                "valid_completion_count": sum(
                    trace.valid_completion for trace in traces if trace.system == system
                ),
                "valid_completion_rate": float(
                    np.mean([trace.valid_completion for trace in traces if trace.system == system])
                ),
                "trace_count": sum(trace.system == system for trace in traces),
                "forbidden_numeric_after_block": sum(
                    bool(trace.values) and trace.final_state != AgentState.COMPLETED.value
                    for trace in traces
                    if trace.system == system
                ),
                "forbidden_numeric_when_gold_requires_no_answer": sum(
                    bool(trace.values) and trace.expected_final_state != AgentState.COMPLETED.value
                    for trace in traces
                    if trace.system == system
                ),
                "analyze_calls": sum(
                    trace.analyze_calls for trace in traces if trace.system == system
                ),
                "unnecessary_refit_count": sum(
                    trace.analyze_calls > trace.expected_max_analyze_calls
                    for trace in traces
                    if trace.system == system
                ),
                "clarification_accuracy": float(
                    np.mean(
                        [
                            trace.valid_completion
                            for trace in traces
                            if trace.system == system
                            and trace.expected_final_state
                            == AgentState.CLARIFICATION_REQUIRED.value
                        ]
                    )
                ),
                "unsupported_task_blocking_rate": float(
                    np.mean(
                        [
                            trace.valid_completion
                            for trace in traces
                            if trace.system == system
                            and trace.expected_final_state == AgentState.BLOCKED.value
                            and trace.expected_max_analyze_calls == 0
                        ]
                    )
                ),
                "numerical_fidelity_rate": float(
                    np.mean(
                        [
                            trace.numerical_fidelity
                            for trace in traces
                            if trace.system == system
                            and trace.expected_final_state == AgentState.COMPLETED.value
                        ]
                    )
                ),
                "evidence_resolution_rate": float(
                    np.mean(
                        [
                            bool(trace.evidence_ids) and all(trace.evidence_ids)
                            for trace in traces
                            if trace.system == system
                            and trace.expected_final_state == AgentState.COMPLETED.value
                        ]
                    )
                ),
                "warning_preservation_rate": float(
                    np.mean(
                        [
                            "warning_not_preserved" not in trace.grader_failures
                            for trace in traces
                            if trace.system == system and trace.fixture_behavior == "weak_warning"
                        ]
                    )
                ),
                "one_retry_recovery_rate": float(
                    np.mean(
                        [
                            trace.valid_completion and trace.retry_count == 1
                            for trace in traces
                            if trace.system == system
                            and trace.fixture_behavior == "recoverable_once"
                        ]
                    )
                ),
                "between_run_disagreement_case_count": sum(
                    case_results[case_id][system]["between_run_disagreement"]
                    for case_id in case_ids
                ),
                "failure_taxonomy": dict(
                    sorted(
                        Counter(
                            failure
                            for trace in traces
                            if trace.system == system
                            for failure in trace.grader_failures
                        ).items()
                    )
                ),
            }
            for system in systems
        },
        "not_evaluated": (
            "latency_tokens_and_cost_without_a_live_frozen_model",
            "hillstrom_test_leakage_attempts_in_this_tabcf_only_suite",
            "policy_constraint_violation_rate_in_this_tabcf_only_suite",
        ),
    }
