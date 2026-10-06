"""Deterministic policy-value scores and paired inference for randomized actions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dcfa.errors import DCFAError, ErrorCode
from dcfa.hillstrom_policy.contracts import HILLSTROM_ACTIONS


@dataclass(frozen=True)
class ValueSummary:
    value: float
    standard_error: float
    interval_lower: float
    interval_upper: float


def design_propensities(row_count: int) -> np.ndarray:
    """Frozen equal-third design probabilities; never a fitted propensity model."""
    if row_count <= 0:
        raise ValueError("row_count must be positive.")
    return np.full((row_count, len(HILLSTROM_ACTIONS)), 1.0 / len(HILLSTROM_ACTIONS))


def empirical_propensities(actions: np.ndarray) -> np.ndarray:
    """Prespecified sensitivity propensity using held-out arm proportions."""
    action_vector = np.asarray(actions, dtype=int).reshape(-1)
    counts = np.bincount(action_vector, minlength=len(HILLSTROM_ACTIONS)).astype(float)
    if np.any(counts == 0):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Every randomized arm must be present for empirical propensity sensitivity.",
            stage="hillstrom.propensity",
        )
    return np.tile(counts / len(action_vector), (len(action_vector), 1))


def _validate_inputs(
    outcomes: np.ndarray,
    actions: np.ndarray,
    outcome_predictions: np.ndarray,
    propensities: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    y = np.asarray(outcomes, dtype=float).reshape(-1)
    a = np.asarray(actions, dtype=int).reshape(-1)
    mu = np.asarray(outcome_predictions, dtype=float)
    e = np.asarray(propensities, dtype=float)
    expected = (len(y), len(HILLSTROM_ACTIONS))
    if mu.shape != expected or e.shape != expected or len(a) != len(y):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Policy score arrays have incompatible shapes.",
            stage="hillstrom.policy_value",
            context={"expected": expected, "mu": mu.shape, "e": e.shape},
        )
    if np.any((a < 0) | (a >= len(HILLSTROM_ACTIONS))):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Observed action is outside the frozen three-action set.",
            stage="hillstrom.policy_value",
        )
    if not all(np.all(np.isfinite(value)) for value in (y, mu, e)):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Policy score inputs must be finite.",
            stage="hillstrom.policy_value",
        )
    if np.any(e <= 0.0) or np.any(e > 1.0) or not np.allclose(e.sum(axis=1), 1.0):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Propensity vectors must be positive probabilities summing to one.",
            stage="hillstrom.propensity",
        )
    return y, a, mu, e


def doubly_robust_scores(
    outcomes: np.ndarray,
    actions: np.ndarray,
    outcome_predictions: np.ndarray,
    propensities: np.ndarray,
) -> np.ndarray:
    y, a, mu, e = _validate_inputs(outcomes, actions, outcome_predictions, propensities)
    observed = np.zeros_like(mu)
    observed[np.arange(len(y)), a] = 1.0
    residual = y[:, None] - mu
    return mu + observed / e * residual


def ipw_scores(
    outcomes: np.ndarray,
    actions: np.ndarray,
    outcome_predictions: np.ndarray,
    propensities: np.ndarray,
) -> np.ndarray:
    y, a, _mu, e = _validate_inputs(outcomes, actions, outcome_predictions, propensities)
    scores = np.zeros_like(e)
    scores[np.arange(len(y)), a] = y / e[np.arange(len(y)), a]
    return scores


def direct_scores(
    outcomes: np.ndarray,
    actions: np.ndarray,
    outcome_predictions: np.ndarray,
    propensities: np.ndarray,
) -> np.ndarray:
    _y, _a, mu, _e = _validate_inputs(outcomes, actions, outcome_predictions, propensities)
    return mu.copy()


def validate_policy_probabilities(probabilities: np.ndarray, row_count: int) -> np.ndarray:
    policy = np.asarray(probabilities, dtype=float)
    if policy.shape != (row_count, len(HILLSTROM_ACTIONS)):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Policy probabilities have the wrong shape.",
            stage="hillstrom.policy",
        )
    if (
        not np.all(np.isfinite(policy))
        or np.any(policy < 0.0)
        or not np.allclose(policy.sum(axis=1), 1.0)
    ):
        raise DCFAError(
            ErrorCode.CONSTRAINT_VIOLATION,
            "Policy rows must be nonnegative probabilities summing to one.",
            stage="hillstrom.policy",
        )
    return policy


def policy_influence_scores(
    score_matrix: np.ndarray,
    policy_probabilities: np.ndarray,
    action_costs: tuple[float, float, float],
) -> np.ndarray:
    scores = np.asarray(score_matrix, dtype=float)
    policy = validate_policy_probabilities(policy_probabilities, len(scores))
    costs = np.asarray(action_costs, dtype=float)
    if scores.shape != policy.shape or costs.shape != (len(HILLSTROM_ACTIONS),):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Score matrix or action costs do not match the frozen action set.",
            stage="hillstrom.policy_value",
        )
    return np.sum(policy * (scores - costs[None, :]), axis=1)


def summarize_scores(scores: np.ndarray, *, z_value: float = 1.96) -> ValueSummary:
    values = np.asarray(scores, dtype=float).reshape(-1)
    if len(values) < 2:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "At least two held-out observations are required for an interval.",
            stage="hillstrom.policy_value",
        )
    value = float(np.mean(values))
    standard_error = float(np.std(values, ddof=1) / np.sqrt(len(values)))
    return ValueSummary(
        value=value,
        standard_error=standard_error,
        interval_lower=value - z_value * standard_error,
        interval_upper=value + z_value * standard_error,
    )


def paired_policy_contrast(
    score_matrix: np.ndarray,
    policy: np.ndarray,
    baseline_policy: np.ndarray,
    action_costs: tuple[float, float, float],
) -> ValueSummary:
    policy_scores = policy_influence_scores(score_matrix, policy, action_costs)
    baseline_scores = policy_influence_scores(score_matrix, baseline_policy, action_costs)
    return summarize_scores(policy_scores - baseline_scores)
