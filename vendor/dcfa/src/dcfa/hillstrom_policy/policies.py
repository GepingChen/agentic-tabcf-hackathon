"""Frozen policy learning with train/validation selection and deterministic refit."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dcfa.errors import DCFAError, ErrorCode
from dcfa.hillstrom_policy.contracts import (
    HILLSTROM_ACTIONS,
    FrozenPolicyArtifact,
    HillstromDataset,
    HillstromPolicySpecification,
    SplitManifest,
)
from dcfa.hillstrom_policy.data import (
    fit_preprocessor,
    transform_features,
    validate_hillstrom_split,
)
from dcfa.hillstrom_policy.estimators import (
    design_propensities,
    doubly_robust_scores,
    policy_influence_scores,
    validate_policy_probabilities,
)


@dataclass(frozen=True)
class PolicyFit:
    artifact: FrozenPolicyArtifact
    best_uniform_action: int
    selected_validation_value: float


def fit_ridge_by_action(
    features: np.ndarray,
    actions: np.ndarray,
    outcomes: np.ndarray,
    *,
    ridge: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(features, dtype=float)
    a = np.asarray(actions, dtype=int).reshape(-1)
    y = np.asarray(outcomes, dtype=float).reshape(-1)
    if x.ndim != 2 or len(x) != len(a) or len(a) != len(y):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Outcome-model arrays have incompatible shapes.",
            stage="hillstrom.outcome_model.fit",
        )
    design = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(design.shape[1]) * float(ridge)
    penalty[0, 0] = 0.0
    coefficients: list[np.ndarray] = []
    for action in range(len(HILLSTROM_ACTIONS)):
        arm = a == action
        if int(np.sum(arm)) <= design.shape[1]:
            raise DCFAError(
                ErrorCode.INVALID_DATA,
                "Each action needs more observations than encoded features.",
                stage="hillstrom.outcome_model.fit",
                context={"action": HILLSTROM_ACTIONS[action], "rows": int(np.sum(arm))},
            )
        gram = design[arm].T @ design[arm] + penalty
        coefficients.append(np.linalg.solve(gram, design[arm].T @ y[arm]))
    stacked = np.vstack(coefficients)
    return stacked[:, 1:], stacked[:, 0]


def predict_action_values(
    features: np.ndarray,
    coefficients: np.ndarray,
    intercepts: np.ndarray,
) -> np.ndarray:
    x = np.asarray(features, dtype=float)
    coef = np.asarray(coefficients, dtype=float)
    intercept = np.asarray(intercepts, dtype=float)
    if coef.shape != (len(HILLSTROM_ACTIONS), x.shape[1]) or intercept.shape != (
        len(HILLSTROM_ACTIONS),
    ):
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Frozen outcome-model dimensions do not match transformed features.",
            stage="hillstrom.outcome_model.predict",
        )
    return x @ coef.T + intercept[None, :]


def uniform_policy(row_count: int, action: int) -> np.ndarray:
    if action not in range(len(HILLSTROM_ACTIONS)):
        raise ValueError("Unknown action index.")
    policy = np.zeros((row_count, len(HILLSTROM_ACTIONS)), dtype=float)
    policy[:, action] = 1.0
    return policy


def enforce_email_capacity(
    policy: np.ndarray,
    action_values: np.ndarray,
    capacity_fraction: float | None,
    *,
    fallback_action: int = 0,
) -> np.ndarray:
    probabilities = validate_policy_probabilities(policy, len(policy)).copy()
    if capacity_fraction is None:
        return probabilities
    if not 0.0 <= capacity_fraction <= 1.0:
        raise DCFAError(
            ErrorCode.CONSTRAINT_VIOLATION,
            "Email capacity fraction must lie in [0, 1].",
            stage="hillstrom.policy.capacity",
        )
    chosen = np.argmax(probabilities, axis=1)
    email_rows = np.flatnonzero(chosen != fallback_action)
    capacity = int(np.floor(capacity_fraction * len(probabilities)))
    if len(email_rows) <= capacity:
        return probabilities
    values = np.asarray(action_values, dtype=float)
    benefits = values[email_rows, chosen[email_rows]] - values[email_rows, fallback_action]
    ranked = email_rows[np.lexsort((email_rows, -benefits))]
    rejected = ranked[capacity:]
    probabilities[rejected] = 0.0
    probabilities[rejected, fallback_action] = 1.0
    return probabilities


def policy_from_values(
    action_values: np.ndarray,
    *,
    uncertainty_threshold: float,
    fallback_action: int = 0,
    capacity_fraction: float | None = None,
) -> np.ndarray:
    values = np.asarray(action_values, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(HILLSTROM_ACTIONS):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Action-value predictions must have one column per categorical action.",
            stage="hillstrom.policy",
        )
    order = np.argsort(values, axis=1, kind="stable")
    best = order[:, -1]
    gap = values[np.arange(len(values)), best] - values[np.arange(len(values)), order[:, -2]]
    best = np.where(gap >= float(uncertainty_threshold), best, fallback_action)
    policy = np.zeros_like(values)
    policy[np.arange(len(values)), best] = 1.0
    return enforce_email_capacity(
        policy,
        values,
        capacity_fraction,
        fallback_action=fallback_action,
    )


def cross_fitted_outcome_predictions(
    features: np.ndarray,
    actions: np.ndarray,
    outcomes: np.ndarray,
    *,
    seed: int,
) -> np.ndarray:
    """Two-fold nuisance predictions used only inside the training partition."""
    x = np.asarray(features, dtype=float)
    a = np.asarray(actions, dtype=int)
    y = np.asarray(outcomes, dtype=float)
    rng = np.random.default_rng(seed)
    fold = np.empty(len(a), dtype=int)
    for action in range(len(HILLSTROM_ACTIONS)):
        arm = rng.permutation(np.flatnonzero(a == action))
        fold[arm[::2]] = 0
        fold[arm[1::2]] = 1
    predictions = np.empty((len(a), len(HILLSTROM_ACTIONS)), dtype=float)
    for held_out in (0, 1):
        fit_rows = fold != held_out
        held_rows = fold == held_out
        coefficients, intercepts = fit_ridge_by_action(x[fit_rows], a[fit_rows], y[fit_rows])
        predictions[held_rows] = predict_action_values(x[held_rows], coefficients, intercepts)
    return predictions


def fit_frozen_policy(
    dataset: HillstromDataset,
    split: SplitManifest,
    specification: HillstromPolicySpecification,
) -> PolicyFit:
    validate_hillstrom_split(split, dataset)
    if dataset.manifest.dataset_hash != specification.dataset_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Policy specification and dataset hashes differ.",
            stage="hillstrom.policy.fit",
        )
    if split.split_manifest_id != specification.split_manifest_id:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Policy specification and split manifest differ.",
            stage="hillstrom.policy.fit",
        )
    fallback_action = HILLSTROM_ACTIONS.index(specification.fallback_action)
    actions = np.asarray(dataset.actions, dtype=int)
    outcomes = np.asarray(dataset.spend, dtype=float)
    train = split.train_indices
    validation = split.validation_indices

    training_preprocessor = fit_preprocessor(dataset, train, fit_split="training")
    x_train = transform_features(dataset, train, training_preprocessor)
    x_validation = transform_features(dataset, validation, training_preprocessor)
    coefficients, intercepts = fit_ridge_by_action(
        x_train,
        actions[np.asarray(train)],
        outcomes[np.asarray(train)],
    )
    validation_predictions = predict_action_values(x_validation, coefficients, intercepts)
    validation_actions = actions[np.asarray(validation)]
    validation_outcomes = outcomes[np.asarray(validation)]
    validation_dr = doubly_robust_scores(
        validation_outcomes,
        validation_actions,
        validation_predictions,
        design_propensities(len(validation)),
    )
    costs = specification.objective.action_costs
    arm_values = [
        float(
            np.mean(
                policy_influence_scores(
                    validation_dr,
                    uniform_policy(len(validation), action),
                    costs,
                )
            )
        )
        for action in range(len(HILLSTROM_ACTIONS))
    ]
    best_uniform_action = int(np.argmax(arm_values))

    candidates: list[tuple[float, float]] = []
    for threshold in sorted(set(specification.uncertainty_threshold_candidates)):
        policy = policy_from_values(
            validation_predictions - np.asarray(costs)[None, :],
            uncertainty_threshold=float(threshold),
            fallback_action=fallback_action,
            capacity_fraction=specification.capacity_fraction,
        )
        value = float(np.mean(policy_influence_scores(validation_dr, policy, costs)))
        candidates.append((value, float(threshold)))
    selected_value, selected_threshold = max(candidates, key=lambda item: (item[0], -item[1]))

    refit_indices = tuple(sorted((*train, *validation)))
    final_preprocessor = fit_preprocessor(
        dataset,
        refit_indices,
        fit_split="training_plus_validation_after_selection",
    )
    x_refit = transform_features(dataset, refit_indices, final_preprocessor)
    final_coefficients, final_intercepts = fit_ridge_by_action(
        x_refit,
        actions[np.asarray(refit_indices)],
        outcomes[np.asarray(refit_indices)],
    )
    artifact = FrozenPolicyArtifact(
        policy_name="uncertainty_aware_personalized",
        policy_class="ridge_outcome_argmax_with_fallback",
        dataset_hash=dataset.manifest.dataset_hash,
        split_manifest_id=split.split_manifest_id,
        preprocessing=final_preprocessor,
        actions=HILLSTROM_ACTIONS,
        coefficients=tuple(tuple(float(value) for value in row) for row in final_coefficients),
        intercepts=tuple(float(value) for value in final_intercepts),
        objective=specification.objective,
        fallback_action=specification.fallback_action,
        uncertainty_method="top_two_net_value_gap",
        uncertainty_threshold=selected_threshold,
        capacity_fraction=specification.capacity_fraction,
        selection_split="validation",
        refit_split="training_plus_validation",
        created_without_test_outcomes=True,
        track=specification.track,
        execution_profile=specification.execution_profile,
        estimator_backend=specification.estimator_backend,
        evidence_status=specification.evidence_status,
        seed=specification.seed,
    )
    return PolicyFit(
        artifact=artifact,
        best_uniform_action=best_uniform_action,
        selected_validation_value=selected_value,
    )


def predict_frozen_policy(
    artifact: FrozenPolicyArtifact,
    features: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    values = predict_action_values(
        features,
        np.asarray(artifact.coefficients),
        np.asarray(artifact.intercepts),
    )
    net_values = values - np.asarray(artifact.objective.action_costs)[None, :]
    probabilities = policy_from_values(
        net_values,
        uncertainty_threshold=artifact.uncertainty_threshold,
        fallback_action=HILLSTROM_ACTIONS.index(artifact.fallback_action),
        capacity_fraction=artifact.capacity_fraction,
    )
    return probabilities, values
