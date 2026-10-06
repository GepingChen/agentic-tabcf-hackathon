"""Deterministic original-unit projections; no estimation, fitting, or grid changes."""

from __future__ import annotations

import math
import re
from dataclasses import asdict
from typing import Any

import numpy as np

from dcfa.errors import DCFAError, ErrorCode
from dcfa.schemas import DistributionRequest


def validate_distribution_request(request: DistributionRequest | None) -> None:
    valid = isinstance(request, DistributionRequest)
    if valid:
        d = request
        values = (*d.prices, *((d.threshold,) if d.threshold is not None else ()))
        valid = (
            len(d.prices) == 2
            and all(
                isinstance(v, (int, float))
                and not isinstance(v, bool)
                and math.isfinite(v)
                and v > 0
                for v in values
            )
            and d.prices[0] < d.prices[1]
            and d.treatment_scale == d.outcome_scale == "stored_natural_log"
            and tuple(d.quantile_levels) in ((0.25, 0.5, 0.75), (0.25, 0.5, 0.75, 0.9))
            and all(
                isinstance(u, str) and re.fullmatch(r"[A-Za-z][A-Za-z /_-]{0,79}", u)
                for u in (d.treatment_units, d.outcome_units)
            )
        )
    if not valid:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Distribution requests require two increasing positive original-unit values, "
            "explicit units, already-natural-log X and Y, and the supported quantiles.",
            stage="specification.units",
        )


def derive_distribution(
    request: DistributionRequest, y_grid, cdf, quantiles, risks
) -> dict[str, Any]:
    """Return the complete CPU projection from the single model-scale prediction bundle."""
    validate_distribution_request(request)
    d = request
    y = np.asarray(y_grid, dtype=float)
    f = np.asarray(cdf, dtype=float)
    qlog = np.asarray(quantiles, dtype=float)
    q = np.exp(qlog)
    axis = np.exp(y)
    widths = np.diff(axis)
    cdf_increments = np.diff(f, axis=1)
    bounded = (qlog <= y[0]) | (qlog >= y[-1])
    if not np.all(np.isfinite(axis)) or not np.all(np.isfinite(q)):
        raise ValueError("Original-unit projection overflowed; no extrapolation is available.")
    if len(axis) < 2 or np.any(widths <= 0.0):
        raise ValueError("The evaluated original-unit outcome grid must be strictly increasing.")
    if np.any(cdf_increments < -1e-12):
        raise ValueError("CDF-derived density requires nondecreasing evaluated CDF curves.")
    # Canonical CDFs are monotone; remove round-off only, without smoothing or extrapolation.
    density = np.maximum(cdf_increments, 0.0) / widths[None, :]
    density_axis = 0.5 * (axis[:-1] + axis[1:])
    if not np.all(np.isfinite(density)):
        raise ValueError("CDF-derived density contains non-finite values.")
    metrics = []

    def add(key, value, units):
        metrics.append({"key": key, "value": float(value), "units": units})
        return key

    rows = []
    for j, level in enumerate(d.quantile_levels):
        keys = [add(f"quantile:{level:g}:{i}", q[i, j], d.outcome_units) for i in range(2)]
        delta = add(f"quantile_difference:{level:g}", q[1, j] - q[0, j], d.outcome_units)
        rows.append(
            {
                "level": level,
                "values": keys,
                "difference": delta,
                "boundary_limited": [bool(v) for v in bounded[:, j]],
            }
        )
    threshold_cdf, probabilities = [], []
    difference = None
    if d.threshold is not None:
        risk = 1.0 - np.asarray(risks, dtype=float)[:, 0]
        threshold_cdf = [
            add(f"threshold_cdf:{i}", float(risks[i][0]), "probability") for i in range(2)
        ]
        probabilities = [add(f"exceedance:{i}", 100 * risk[i], "percent") for i in range(2)]
        difference = add("exceedance_difference", 100 * (risk[1] - risk[0]), "percentage points")
    gap_key, summary = None, ""
    # Retain the old projection only for verification of saved four-quantile artifacts.
    # New dialogue requests use quartiles and never generate comparative narratives.
    if tuple(d.quantile_levels) == (0.25, 0.5, 0.75, 0.9):
        gap = (q[1, 3] - q[0, 3]) - (q[1, 1] - q[0, 1])
        gap_key = add("upper_minus_middle_change", gap, d.outcome_units)
        limited = bool(np.any(bounded[:, [1, 3]]))
        summary = (
            "Median or upper quantile is boundary-limited. The gap change is a clipped-grid "
            "description; no resolved upper-versus-middle conclusion is available."
            if limited
            else "The estimated upper-minus-median gap "
            + ("narrows." if gap < 0 else "widens." if gap > 0 else "is unchanged.")
        )
        delta = q[1] - q[0]
        if not limited:
            if delta[1] < 0 and delta[3] < 0:
                summary += " Both median and upper quantile decrease."
            elif delta[1] > 0 and delta[3] > 0:
                summary += " Both median and upper quantile increase."
            else:
                summary += " Median and upper changes have mixed signs or include zero."
            summary += (
                " The upper change has "
                + (
                    "larger"
                    if abs(delta[3]) > abs(delta[1])
                    else "smaller"
                    if abs(delta[3]) < abs(delta[1])
                    else "equal"
                )
                + " absolute magnitude relative to the median change."
            )
        fd = f[1] - f[0]
        crossing = bool(np.any(fd > 0) and np.any(fd < 0))
        summary += (
            " The evaluated CDF curves cross."
            if crossing
            else " No crossing is seen on the evaluated grid; this does not prove dominance."
        )
    curves = []
    for i in range(2):
        keys = [add(f"cdf:{i}:{j}", value, "probability") for j, value in enumerate(f[i])]
        curves.append({"price": d.prices[i], "cdf": keys})
    densities = []
    density_units = "probability density"
    for i in range(2):
        keys = [add(f"density:{i}:{j}", value, density_units) for j, value in enumerate(density[i])]
        densities.append({"price": d.prices[i], "pdf": keys})
    return {
        "request": asdict(d),
        "outcome_axis": axis.tolist(),
        "curves": curves,
        "density_axis": density_axis.tolist(),
        "densities": densities,
        "density_method": "finite_difference_of_cdf_on_evaluated_outcome_grid",
        "quantiles": rows,
        "probabilities": probabilities,
        "probability_difference": difference,
        "gap_change": gap_key,
        "threshold_cdf": threshold_cdf,
        "boundary_limited": bool(np.any(bounded)),
        "summary": summary,
        "metrics": metrics,
    }
