"""Four auditable semi-synthetic policy DGPs with known conditional utilities."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dcfa.canonical import content_id
from dcfa.errors import DCFAError, ErrorCode
from dcfa.hillstrom_policy.contracts import HILLSTROM_ACTIONS, HillstromDataset, SplitManifest
from dcfa.hillstrom_policy.data import (
    fit_preprocessor,
    transform_features,
    validate_hillstrom_split,
)
from dcfa.hillstrom_policy.policies import (
    enforce_email_capacity,
    fit_ridge_by_action,
    policy_from_values,
    predict_action_values,
    uniform_policy,
)

SEMISYNTHETIC_SCENARIOS = (
    "no_heterogeneity",
    "crossing_campaigns",
    "weak_effects",
    "cost_capacity_reversal",
)


@dataclass(frozen=True)
class SemiSyntheticWorld:
    scenario: str
    source_index_hash: str
    data_label: str
    features: np.ndarray
    conditional_gross_spend: np.ndarray
    conditional_utility: np.ndarray
    potential_outcomes: np.ndarray
    action_costs: tuple[float, float, float]
    capacity_fraction: float | None


@dataclass(frozen=True)
class SemiSyntheticMetrics:
    scenario: str
    replication: int
    data_label: str
    oracle_value: float
    learned_policy_value: float
    best_uniform_value: float
    learned_regret: float
    best_uniform_regret: float
    optimal_action_accuracy: float
    fallback_rate: float
    abstention_coverage: float
    selective_regret: float
    fallback_inclusive_value: float
    action_value_gap_mae: float
    action_confusion_matrix: tuple[tuple[float, ...], ...]
    constraint_violations: int
    result_id: str


def _sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(value, -30.0, 30.0)))


def sample_world(
    dataset: HillstromDataset,
    split: SplitManifest,
    *,
    scenario: str,
    row_count: int,
    seed: int,
) -> SemiSyntheticWorld:
    if scenario not in SEMISYNTHETIC_SCENARIOS:
        raise ValueError(f"Unknown semi-synthetic scenario: {scenario}")
    if row_count < 120:
        raise ValueError("Semi-synthetic worlds require at least 120 rows.")
    rng = np.random.default_rng(seed)
    preprocessing = fit_preprocessor(dataset, split.train_indices, fit_split="source_training_only")
    sampled_indices = tuple(
        int(value) for value in rng.choice(split.train_indices, size=row_count, replace=True)
    )
    features = transform_features(dataset, sampled_indices, preprocessing)
    x0 = features[:, 0] if features.shape[1] else np.zeros(row_count)
    x1 = features[:, 1] if features.shape[1] > 1 else np.zeros(row_count)
    baseline_logit = -1.25 + 0.20 * x0 + 0.15 * x1
    baseline_log_spend = 3.0 + 0.10 * x1
    action_costs = (0.0, 0.0, 0.0)
    capacity: float | None = None

    if scenario == "no_heterogeneity":
        p_shift = np.tile(np.array([0.0, 0.15, 0.35]), (row_count, 1))
        r_shift = np.tile(np.array([0.0, 0.04, 0.12]), (row_count, 1))
    elif scenario == "crossing_campaigns":
        p_shift = np.column_stack([np.zeros(row_count), 0.25 + 0.55 * x0, 0.25 - 0.55 * x0])
        r_shift = np.column_stack([np.zeros(row_count), 0.08 + 0.12 * x0, 0.08 - 0.12 * x0])
    elif scenario == "weak_effects":
        p_shift = np.column_stack([np.zeros(row_count), 0.04 + 0.05 * x0, 0.03 - 0.05 * x0])
        r_shift = np.column_stack([np.zeros(row_count), 0.015 + 0.01 * x1, 0.012 - 0.01 * x1])
    else:
        p_shift = np.column_stack([np.zeros(row_count), 0.28 + 0.45 * x0, 0.36 - 0.35 * x0])
        r_shift = np.column_stack([np.zeros(row_count), 0.10 + 0.08 * x0, 0.14 - 0.06 * x0])
        action_costs = (0.0, 2.0, 3.5)
        capacity = 0.35

    probabilities = _sigmoid(baseline_logit[:, None] + p_shift)
    log_positive_mean = baseline_log_spend[:, None] + r_shift
    sigma = np.array([0.55, 0.58, 0.60])
    gross_mean = probabilities * np.exp(log_positive_mean + 0.5 * sigma[None, :] ** 2)
    utility = gross_mean - np.asarray(action_costs)[None, :]
    conversion = rng.uniform(size=(row_count, len(HILLSTROM_ACTIONS))) < probabilities
    positive_spend = np.exp(
        log_positive_mean + rng.normal(size=(row_count, len(HILLSTROM_ACTIONS))) * sigma
    )
    potential_outcomes = conversion * positive_spend
    data_label = (
        "hillstrom_calibrated_semisynthetic"
        if dataset.manifest.source_kind == "real_randomized_experiment"
        else "development_synthetic_not_hillstrom_calibrated"
    )
    return SemiSyntheticWorld(
        scenario=scenario,
        source_index_hash=content_id("source_rows", sampled_indices),
        data_label=data_label,
        features=features,
        conditional_gross_spend=gross_mean,
        conditional_utility=utility,
        potential_outcomes=potential_outcomes,
        action_costs=action_costs,
        capacity_fraction=capacity,
    )


def _true_policy_value(policy: np.ndarray, utility: np.ndarray) -> float:
    return float(np.mean(np.sum(policy * utility, axis=1)))


def run_replication(
    dataset: HillstromDataset,
    split: SplitManifest,
    *,
    scenario: str,
    replication: int,
    row_count: int = 1200,
    seed: int = 1729,
) -> SemiSyntheticMetrics:
    world = sample_world(
        dataset,
        split,
        scenario=scenario,
        row_count=row_count,
        seed=seed + replication * 1009,
    )
    rng = np.random.default_rng(seed + replication * 2027 + 17)
    order = rng.permutation(row_count)
    training_rows = order[: row_count // 2]
    evaluation_rows = order[row_count // 2 :]
    randomized_actions = rng.integers(0, len(HILLSTROM_ACTIONS), size=len(training_rows))
    observed_outcomes = world.potential_outcomes[
        training_rows,
        randomized_actions,
    ]
    coefficients, intercepts = fit_ridge_by_action(
        world.features[training_rows],
        randomized_actions,
        observed_outcomes,
        ridge=3.0,
    )
    predicted_gross = predict_action_values(
        world.features[evaluation_rows], coefficients, intercepts
    )
    predicted_net = predicted_gross - np.asarray(world.action_costs)[None, :]
    learned = policy_from_values(
        predicted_net,
        uncertainty_threshold=0.1,
        capacity_fraction=world.capacity_fraction,
    )
    evaluation_utility = world.conditional_utility[evaluation_rows]
    oracle = policy_from_values(
        evaluation_utility,
        uncertainty_threshold=0.0,
        capacity_fraction=world.capacity_fraction,
    )

    training_arm_means = np.array(
        [
            float(np.mean(observed_outcomes[randomized_actions == action]))
            - world.action_costs[action]
            for action in range(len(HILLSTROM_ACTIONS))
        ]
    )
    best_uniform = uniform_policy(len(evaluation_rows), int(np.argmax(training_arm_means)))
    if world.capacity_fraction is not None:
        best_uniform = enforce_email_capacity(
            best_uniform,
            predicted_net,
            world.capacity_fraction,
        )
    oracle_value = _true_policy_value(oracle, evaluation_utility)
    learned_value = _true_policy_value(learned, evaluation_utility)
    uniform_value = _true_policy_value(best_uniform, evaluation_utility)
    learned_regret = oracle_value - learned_value
    uniform_regret = oracle_value - uniform_value
    if learned_regret < -1e-10 or uniform_regret < -1e-10:
        raise DCFAError(
            ErrorCode.CONSTRAINT_VIOLATION,
            "A feasible policy exceeded the same-constraint oracle.",
            stage="hillstrom.semisynthetic",
        )
    oracle_actions = np.argmax(oracle, axis=1)
    learned_actions = np.argmax(learned, axis=1)
    unconstrained_oracle_row_value = np.max(evaluation_utility, axis=1)
    learned_row_value = evaluation_utility[np.arange(len(evaluation_rows)), learned_actions]
    selected_rows = learned_actions != 0
    selective_regret = (
        float(
            np.mean(
                unconstrained_oracle_row_value[selected_rows] - learned_row_value[selected_rows]
            )
        )
        if np.any(selected_rows)
        else 0.0
    )
    true_sorted = np.sort(evaluation_utility, axis=1)
    predicted_sorted = np.sort(predicted_net, axis=1)
    true_gap = true_sorted[:, -1] - true_sorted[:, -2]
    predicted_gap = predicted_sorted[:, -1] - predicted_sorted[:, -2]
    confusion = tuple(
        tuple(
            float(np.mean((oracle_actions == truth) & (learned_actions == predicted)))
            for predicted in range(len(HILLSTROM_ACTIONS))
        )
        for truth in range(len(HILLSTROM_ACTIONS))
    )
    allocated_email = int(np.sum(learned_actions != 0))
    allowed_email = (
        len(learned_actions)
        if world.capacity_fraction is None
        else int(np.floor(world.capacity_fraction * len(learned_actions)))
    )
    payload = {
        "scenario": scenario,
        "replication": replication,
        "data_label": world.data_label,
        "oracle_value": oracle_value,
        "learned_policy_value": learned_value,
        "best_uniform_value": uniform_value,
        "learned_regret": max(0.0, learned_regret),
        "best_uniform_regret": max(0.0, uniform_regret),
        "optimal_action_accuracy": float(np.mean(oracle_actions == learned_actions)),
        "fallback_rate": float(np.mean(learned_actions == 0)),
        "abstention_coverage": float(np.mean(learned_actions == 0)),
        "selective_regret": selective_regret,
        "fallback_inclusive_value": learned_value,
        "action_value_gap_mae": float(np.mean(np.abs(predicted_gap - true_gap))),
        "action_confusion_matrix": confusion,
        "constraint_violations": max(0, allocated_email - allowed_email),
    }
    return SemiSyntheticMetrics(result_id=content_id("semisynth", payload), **payload)


def run_four_scenarios(
    dataset: HillstromDataset,
    split: SplitManifest,
    *,
    replications: int,
    row_count: int,
    seed: int,
) -> tuple[SemiSyntheticMetrics, ...]:
    if replications <= 0:
        raise ValueError("replications must be positive.")
    validate_hillstrom_split(split, dataset)
    return tuple(
        run_replication(
            dataset,
            split,
            scenario=scenario,
            replication=replication,
            row_count=row_count,
            seed=seed,
        )
        for scenario in SEMISYNTHETIC_SCENARIOS
        for replication in range(replications)
    )
