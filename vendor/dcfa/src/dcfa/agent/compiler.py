"""Deterministic request-to-specification compiler for TabCF Analyst v1."""

from __future__ import annotations

import math
from dataclasses import dataclass

from dcfa.canonical import content_id
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import DCFAError, ErrorCode
from dcfa.schemas import AnalysisSpecification, CausalRoles, DistributionRequest, QuerySpecification

SUPPORTED_OBJECTIVES = frozenset(
    {
        "mean",
        "quantile",
        "risk",
        "mean_contrast",
        "quantile_contrast",
        "risk_contrast",
        "distribution",
    }
)


@dataclass(frozen=True)
class CompilationRequest:
    dataset_hash: str
    outcome: str | None
    treatment: str | None
    instrument: str | None
    objective: str | None
    intervention_grid: tuple[float, ...]
    x: float | None
    comparison_x: float | None = None
    level: float | None = None
    threshold: float | None = None
    baseline_covariates: tuple[str, ...] = ()
    treatment_type: str = "continuous"
    units: str = "outcome_units"
    confirmed_by_user: bool = True
    execution_profile: ExecutionProfile = ExecutionProfile.LOCAL_DEVELOPMENT
    estimator_backend: EstimatorBackend = EstimatorBackend.SKLEARN_QUANTILE_FALLBACK
    evidence_status: EvidenceStatus = EvidenceStatus.DEVELOPMENT_ONLY
    backend_parameters: tuple[tuple[str, str], ...] = ()
    seed: int = 1729
    distribution: DistributionRequest | None = None


@dataclass(frozen=True)
class CompilationOutcome:
    specification: AnalysisSpecification | None
    clarification_questions: tuple[str, ...]

    @property
    def requires_clarification(self) -> bool:
        return bool(self.clarification_questions)


class SpecificationCompiler:
    def compile(self, request: CompilationRequest) -> CompilationOutcome:
        if request.baseline_covariates:
            raise DCFAError(
                ErrorCode.UNSUPPORTED_BASELINE_COVARIATES,
                "TabCF Analyst v1 cannot compile a specification with baseline covariates W.",
                stage="compiler.scope",
                context={"baseline_covariates": list(request.baseline_covariates)},
            )
        if request.treatment_type != "continuous":
            raise DCFAError(
                ErrorCode.UNSUPPORTED_TREATMENT,
                "TabCF Analyst v1 cannot compile a non-continuous treatment specification.",
                stage="compiler.scope",
                context={"treatment_type": request.treatment_type},
            )

        if request.objective == "distribution":
            from dcfa.tabcf_iv.distribution import validate_distribution_request

            validate_distribution_request(request.distribution)
            d = request.distribution
            assert d is not None
            expected_grid = tuple(math.log(p) for p in d.prices)
            if (
                request.intervention_grid != expected_grid
                or request.x != expected_grid[1]
                or request.comparison_x != expected_grid[0]
            ):
                raise DCFAError(
                    ErrorCode.INVALID_SPECIFICATION,
                    "Exact original-unit interventions must be logged once; "
                    "no symbolic substitution.",
                    stage="compiler.units",
                )
        elif request.distribution is not None:
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                "Distribution metadata requires the distribution objective.",
                stage="compiler.units",
            )
        questions: list[str] = []
        if not request.outcome:
            questions.append("Which single continuous outcome column is Y?")
        if not request.treatment:
            questions.append("Which single continuous treatment column is X?")
        if not request.instrument:
            questions.append("Which scalar instrument column is Z?")
        if request.objective is None:
            questions.append("Should the result be a mean, quantile, risk, or explicit contrast?")
        elif request.objective not in SUPPORTED_OBJECTIVES:
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                f"Unsupported TabCF v1 objective: {request.objective}.",
                stage="compiler.objective",
            )
        if request.x is None:
            questions.append("Which supported intervention value x should be evaluated?")
        if request.objective in {"quantile", "quantile_contrast"} and request.level is None:
            questions.append("Which quantile level tau in (0, 1) should be evaluated?")
        if request.objective in {"risk", "risk_contrast"} and request.threshold is None:
            questions.append("Which outcome threshold defines the requested risk?")
        if request.objective in {
            "mean_contrast",
            "quantile_contrast",
            "risk_contrast",
            "distribution",
        }:
            if request.comparison_x is None:
                questions.append("Which comparison intervention defines x minus comparison_x?")
        if questions:
            return CompilationOutcome(None, tuple(questions))

        assert request.outcome is not None
        assert request.treatment is not None
        assert request.instrument is not None
        assert request.objective is not None
        assert request.x is not None
        query_payload = {
            "objective": request.objective,
            "x": request.x,
            "comparison_x": request.comparison_x,
            "level": request.level,
            "threshold": request.threshold,
            "units": request.units,
        }
        query = QuerySpecification(
            query_id=content_id("query", query_payload),
            kind=request.objective,
            x=float(request.x),
            comparison_x=(None if request.comparison_x is None else float(request.comparison_x)),
            level=None if request.level is None else float(request.level),
            threshold=None if request.threshold is None else float(request.threshold),
            units=request.units,
        )
        quantile_levels = (float(request.level),) if request.level is not None else (0.1, 0.5, 0.9)
        risk_thresholds = (float(request.threshold),) if request.threshold is not None else ()
        if request.distribution is not None:
            quantile_levels = request.distribution.quantile_levels
            risk_thresholds = (
                (math.log(request.distribution.threshold),)
                if request.distribution.threshold is not None
                else ()
            )
        specification = AnalysisSpecification(
            dataset_hash=request.dataset_hash,
            roles=CausalRoles(
                outcome=request.outcome,
                treatment=request.treatment,
                instrument=request.instrument,
                baseline_covariates=(),
                treatment_type=request.treatment_type,
            ),
            queries=(query,),
            intervention_grid=request.intervention_grid,
            quantile_levels=quantile_levels,
            risk_thresholds=risk_thresholds,
            execution_profile=request.execution_profile,
            estimator_backend=request.estimator_backend,
            evidence_status=request.evidence_status,
            track=Track.TABCF_IV,
            confirmed_by_user=request.confirmed_by_user,
            backend_parameters=request.backend_parameters,
            seed=request.seed,
            distribution=request.distribution,
        )
        return CompilationOutcome(specification, ())
