"""Deterministic empirical diagnostics and joint intervention-support checks."""

from __future__ import annotations

import numpy as np
from scipy.stats import cramervonmises

from dcfa.constants import SupportStatus, WarningSeverity
from dcfa.schemas import DiagnosticBundle, SupportAssessment, WarningRecord


def compute_diagnostics(
    z: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    control_rank: np.ndarray,
) -> tuple[DiagnosticBundle, tuple[WarningRecord, ...]]:
    z_arr = np.asarray(z, dtype=float).reshape(-1)
    x_arr = np.asarray(x, dtype=float).reshape(-1)
    y_arr = np.asarray(y, dtype=float).reshape(-1)
    v_arr = np.asarray(control_rank, dtype=float).reshape(-1)

    design = np.column_stack([np.ones(len(z_arr)), z_arr])
    coefficients, *_ = np.linalg.lstsq(design, x_arr, rcond=None)
    fitted_x = design @ coefficients
    residual_x = x_arr - fitted_x
    sse = float(np.sum(residual_x**2))
    sst = float(np.sum((x_arr - np.mean(x_arr)) ** 2))
    r2 = 0.0 if sst <= 0.0 else max(0.0, min(1.0, 1.0 - sse / sst))
    denominator_df = max(len(x_arr) - 2, 1)
    first_stage_f = float((r2 / max(1.0 - r2, 1e-12)) * denominator_df)

    cvm = float(cramervonmises(np.clip(v_arr, 0.0, 1.0), "uniform").statistic)

    conditional_design = np.column_stack([np.ones(len(x_arr)), x_arr, v_arr])
    y_coefficients, *_ = np.linalg.lstsq(conditional_design, y_arr, rcond=None)
    z_coefficients, *_ = np.linalg.lstsq(conditional_design, z_arr, rcond=None)
    y_residual = y_arr - conditional_design @ y_coefficients
    z_residual = z_arr - conditional_design @ z_coefficients
    residual_score = float(abs(np.corrcoef(y_residual, z_residual)[0, 1]))
    if not np.isfinite(residual_score):
        residual_score = 1.0

    diagnostics = DiagnosticBundle(
        first_stage_f=first_stage_f,
        first_stage_r2=float(r2),
        control_rank_cvm=cvm,
        control_rank_mean=float(np.mean(v_arr)),
        residual_dependence_score=residual_score,
    )
    warnings: list[WarningRecord] = []
    if first_stage_f < 10.0:
        warnings.append(
            WarningRecord(
                code="WEAK_FIRST_STAGE_EMPIRICAL_WARNING",
                message=(
                    "The empirical linear first-stage diagnostic is below the development "
                    "warning threshold; this does not prove invalidity."
                ),
                severity=WarningSeverity.WARNING,
                source="diagnostics.relevance",
            )
        )
    if cvm > 0.5:
        warnings.append(
            WarningRecord(
                code="CONTROL_RANK_CALIBRATION_WARNING",
                message=(
                    "The estimated control rank departs from a uniform reference in this "
                    "development check."
                ),
                severity=WarningSeverity.WARNING,
                source="diagnostics.control_rank",
            )
        )
    if residual_score > 0.2:
        warnings.append(
            WarningRecord(
                code="RESIDUAL_DEPENDENCE_EMPIRICAL_WARNING",
                message=(
                    "Residual dependence remains in an empirical linear diagnostic; this check "
                    "does not establish or refute instrument validity."
                ),
                severity=WarningSeverity.WARNING,
                source="diagnostics.residual_dependence",
            )
        )
    return diagnostics, tuple(warnings)


def assess_support(
    x: np.ndarray,
    control_rank: np.ndarray,
    intervention_grid: tuple[float, ...],
) -> tuple[SupportAssessment, ...]:
    """Assess marginal X range and local V-bin coverage at every intervention."""
    x_arr = np.asarray(x, dtype=float).reshape(-1)
    v_arr = np.asarray(control_rank, dtype=float).reshape(-1)
    recommended = tuple(float(value) for value in np.quantile(x_arr, [0.01, 0.99]))
    strict = tuple(float(value) for value in np.quantile(x_arr, [0.05, 0.95]))
    neighborhood_size = min(len(x_arr), max(40, int(np.ceil(0.15 * len(x_arr)))))
    assessments: list[SupportAssessment] = []
    for requested_x in intervention_grid:
        distances = np.abs(x_arr - float(requested_x))
        neighbor_indices = np.argpartition(distances, neighborhood_size - 1)[:neighborhood_size]
        local_v = np.clip(v_arr[neighbor_indices], 0.0, 1.0)
        occupied_bins = np.unique(np.minimum((local_v * 10).astype(int), 9)).size
        coverage_score = float(occupied_bins / 10.0)
        inside_strict = strict[0] <= requested_x <= strict[1]
        inside_recommended = recommended[0] <= requested_x <= recommended[1]
        if inside_strict and coverage_score >= 0.6:
            status = SupportStatus.SUPPORTED
            reason = "Inside the strict X interval with adequate local control-rank bin coverage."
        elif inside_recommended and coverage_score >= 0.4:
            status = SupportStatus.WEAK_SUPPORT
            reason = "Inside the recommended X interval but outside a strict support condition."
        else:
            status = SupportStatus.UNSUPPORTED
            reason = "Outside the supported X range or lacking local control-rank coverage."
        assessments.append(
            SupportAssessment(
                x=float(requested_x),
                status=status,
                coverage_score=coverage_score,
                recommended_interval=recommended,
                strict_interval=strict,
                reason=reason,
            )
        )
    return tuple(assessments)
