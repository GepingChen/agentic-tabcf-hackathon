"""Canonical CDF coherence and deterministic derived estimands."""

from __future__ import annotations

import numpy as np


def canonicalize_cdf(cdf: np.ndarray) -> np.ndarray:
    matrix = np.asarray(cdf, dtype=float)
    if matrix.ndim != 2:
        raise ValueError(f"Interventional CDF must be a 2D matrix, got {matrix.shape}.")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Interventional CDF contains non-finite values.")
    return np.maximum.accumulate(np.clip(matrix, 0.0, 1.0), axis=1)


def invert_cdf(
    cdf: np.ndarray,
    y_grid: np.ndarray,
    levels: tuple[float, ...],
) -> np.ndarray:
    matrix = canonicalize_cdf(cdf)
    y = np.asarray(y_grid, dtype=float).reshape(-1)
    if matrix.shape[1] != len(y) or np.any(np.diff(y) <= 0.0):
        raise ValueError("CDF columns and strictly increasing y_grid must align.")
    output = np.empty((matrix.shape[0], len(levels)), dtype=float)
    for row_index, row in enumerate(matrix):
        unique_cdf, unique_indices = np.unique(row, return_index=True)
        unique_y = y[unique_indices]
        for level_index, level in enumerate(levels):
            output[row_index, level_index] = float(
                np.interp(float(level), unique_cdf, unique_y, left=y[0], right=y[-1])
            )
    return np.maximum.accumulate(output, axis=1)


def interpolate_risks(
    cdf: np.ndarray,
    y_grid: np.ndarray,
    thresholds: tuple[float, ...],
) -> np.ndarray:
    matrix = canonicalize_cdf(cdf)
    y = np.asarray(y_grid, dtype=float).reshape(-1)
    return np.asarray(
        [
            [
                float(np.interp(threshold, y, row, left=row[0], right=row[-1]))
                for threshold in thresholds
            ]
            for row in matrix
        ],
        dtype=float,
    )


def exact_grid_index(grid: tuple[float, ...], value: float, *, tolerance: float = 1e-10) -> int:
    distances = np.abs(np.asarray(grid, dtype=float) - float(value))
    index = int(np.argmin(distances))
    if distances[index] > tolerance:
        raise ValueError(f"Requested x={value} is not an exact intervention-grid point.")
    return index
