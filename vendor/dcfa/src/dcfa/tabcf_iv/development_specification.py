"""Explicit development-only no-W TabCF IV specification fixture."""

from __future__ import annotations

from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile
from dcfa.schemas import AnalysisSpecification, CausalRoles, QuerySpecification


def development_specification(
    *,
    dataset_hash: str,
    x_values: tuple[float, ...],
    outcome_threshold: float,
    seed: int,
    baseline_covariates: tuple[str, ...] = (),
    treatment_type: str = "continuous",
) -> AnalysisSpecification:
    return AnalysisSpecification(
        dataset_hash=dataset_hash,
        roles=CausalRoles(
            outcome="Y",
            treatment="X",
            instrument="Z",
            baseline_covariates=baseline_covariates,
            treatment_type=treatment_type,
        ),
        intervention_grid=x_values,
        quantile_levels=(0.1, 0.5, 0.9),
        risk_thresholds=(float(outcome_threshold),),
        queries=(
            QuerySpecification("mean_mid", "mean", x=x_values[2], units="Y_units"),
            QuerySpecification(
                "median_high_minus_low",
                "quantile_contrast",
                x=x_values[3],
                comparison_x=x_values[1],
                level=0.5,
                units="Y_units",
            ),
            QuerySpecification(
                "risk_mid",
                "risk",
                x=x_values[2],
                threshold=float(outcome_threshold),
                units="probability",
            ),
        ),
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
        seed=seed,
    )
