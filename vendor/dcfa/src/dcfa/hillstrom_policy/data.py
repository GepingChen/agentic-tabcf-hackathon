"""Provenance, immutable splitting, preprocessing, and test-outcome access gates."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from dcfa.canonical import file_sha256, is_sha256_digest, sha256_digest
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import DCFAError, ErrorCode
from dcfa.hillstrom_policy.contracts import (
    HILLSTROM_ACTIONS,
    POST_TREATMENT_COLUMNS,
    FrozenPolicyArtifact,
    HillstromDataManifest,
    HillstromDataset,
    PreprocessingArtifact,
    SplitManifest,
)

_ACTION_ENCODING = {
    "No E-Mail": 0,
    "Mens E-Mail": 1,
    "Womens E-Mail": 2,
    "no_email": 0,
    "mens_email": 1,
    "womens_email": 2,
}
_NUMERIC_FEATURES = frozenset({"recency", "history", "mens", "womens", "newbie"})
_PRIMARY_FEATURES = ("recency", "history", "mens", "womens", "zip_code", "newbie", "channel")


def _validate_provenance(exact_source: str, retrieval_date: str, license_note: str) -> None:
    values = {
        "exact_source": exact_source,
        "retrieval_date": retrieval_date,
        "license_note": license_note,
    }
    missing = [name for name, value in values.items() if not str(value).strip()]
    if missing:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Real Hillstrom input requires explicit source, retrieval date, and usage note.",
            stage="hillstrom.data.provenance",
            context={"missing": missing},
        )


def _dataset_payload(dataset: HillstromDataset) -> dict[str, object]:
    return {
        "feature_columns": dataset.feature_columns,
        "actions": dataset.actions,
        "spend": dataset.spend,
        "conversion": dataset.conversion,
        "visit": dataset.visit,
    }


def validate_hillstrom_dataset(dataset: HillstromDataset) -> None:
    """Validate raw values and bind them to the immutable data manifest."""
    manifest = dataset.manifest
    provenance_fields = (
        manifest.dataset_id,
        manifest.exact_source,
        manifest.retrieval_date,
        manifest.license_note,
    )
    if any(not value.strip() for value in provenance_fields) or not is_sha256_digest(
        manifest.raw_file_hash
    ):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom data manifest has incomplete provenance or an invalid raw-file hash.",
            stage="hillstrom.data.provenance",
        )
    if manifest.source_kind not in {
        "real_randomized_experiment",
        "development_synthetic_rct_not_hillstrom",
    }:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom data source kind is outside the frozen real/development contracts.",
            stage="hillstrom.data.provenance",
        )
    allowed_markers = {
        (ExecutionProfile.LOCAL_DEVELOPMENT, EvidenceStatus.DEVELOPMENT_ONLY),
        (ExecutionProfile.LOCKED_EVALUATION, EvidenceStatus.ELIGIBLE_FOR_RELEASE),
    }
    if (
        manifest.track is not Track.HILLSTROM_POLICY
        or manifest.estimator_backend is not EstimatorBackend.SKLEARN_POLICY
        or (manifest.execution_profile, manifest.evidence_status) not in allowed_markers
    ):
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "Hillstrom manifest markers do not form an allowed Track H contract.",
            stage="hillstrom.data.provenance",
        )
    required_columns = set(_PRIMARY_FEATURES) | {"segment", "visit", "conversion", "spend"}
    if len(manifest.column_names) != len(set(manifest.column_names)) or not required_columns <= set(
        manifest.column_names
    ):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom manifest does not contain one unambiguous frozen input schema.",
            stage="hillstrom.data.provenance",
        )
    n = dataset.row_count
    if n == 0:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom data must contain observations.",
            stage="hillstrom.data.validation",
        )
    lengths = {
        "actions": len(dataset.actions),
        "spend": len(dataset.spend),
        "conversion": len(dataset.conversion),
        "visit": len(dataset.visit),
        **{name: len(values) for name, values in dataset.feature_columns},
    }
    if any(length != n for length in lengths.values()):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom columns have inconsistent row counts.",
            stage="hillstrom.data.validation",
            context={"lengths": lengths},
        )
    forbidden = sorted(set(dataset.feature_names) & POST_TREATMENT_COLUMNS)
    if forbidden or "history_segment" in dataset.feature_names:
        raise DCFAError(
            ErrorCode.SPLIT_LEAKAGE,
            "Post-treatment outcomes and history_segment are forbidden primary policy features.",
            stage="hillstrom.data.features",
            context={"forbidden_features": forbidden},
        )
    invalid_actions = sorted(set(dataset.actions) - set(range(len(HILLSTROM_ACTIONS))))
    if invalid_actions:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom actions must remain categorical with exactly the frozen three-arm encoding.",
            stage="hillstrom.data.actions",
            context={"invalid_actions": invalid_actions},
        )
    if set(dataset.actions) != {0, 1, 2}:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "All three randomized Hillstrom arms must be present.",
            stage="hillstrom.data.actions",
        )
    if dataset.feature_names != _PRIMARY_FEATURES:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom primary features must match the frozen pre-treatment schema exactly.",
            stage="hillstrom.data.features",
            context={
                "expected_features": list(_PRIMARY_FEATURES),
                "observed_features": list(dataset.feature_names),
            },
        )
    numeric_columns = {
        "spend": np.asarray(dataset.spend, dtype=float),
        "conversion": np.asarray(dataset.conversion, dtype=float),
        "visit": np.asarray(dataset.visit, dtype=float),
    }
    numeric_columns.update(
        {
            name: np.asarray(values, dtype=float)
            for name, values in dataset.feature_columns
            if name in _NUMERIC_FEATURES
        }
    )
    invalid_numeric = sorted(
        name for name, values in numeric_columns.items() if not np.all(np.isfinite(values))
    )
    blank_categorical = sorted(
        name
        for name, values in dataset.feature_columns
        if name not in _NUMERIC_FEATURES and any(not str(value).strip() for value in values)
    )
    if invalid_numeric or blank_categorical:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom policy input fails closed on missing or non-finite values.",
            stage="hillstrom.data.missingness",
            context={
                "invalid_numeric_columns": invalid_numeric,
                "blank_categorical_columns": blank_categorical,
            },
        )
    if np.any(numeric_columns["spend"] < 0.0) or any(
        not set(np.unique(numeric_columns[name])) <= {0.0, 1.0} for name in ("conversion", "visit")
    ):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Spend must be nonnegative and conversion/visit must be binary.",
            stage="hillstrom.data.outcomes",
        )
    observed_hash = sha256_digest(_dataset_payload(dataset))
    expected_arm_counts = tuple(
        (name, int(np.sum(np.asarray(dataset.actions, dtype=int) == index)))
        for index, name in enumerate(HILLSTROM_ACTIONS)
    )
    if observed_hash != manifest.dataset_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Hillstrom raw columns do not match the immutable data manifest hash.",
            stage="hillstrom.data.hash",
            context={"expected": manifest.dataset_hash, "observed": observed_hash},
        )
    if manifest.row_count != n or manifest.arm_counts != expected_arm_counts:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Hillstrom manifest row count or arm counts do not match the raw columns.",
            stage="hillstrom.data.manifest",
        )


def _parse_numeric_column(rows: tuple[dict[str, str], ...], name: str) -> tuple[float, ...]:
    try:
        return tuple(float(row[name]) for row in rows)
    except (TypeError, ValueError) as exc:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            f"Hillstrom numeric column {name} contains an invalid or missing value.",
            stage="hillstrom.data.missingness",
            context={"column": name},
        ) from exc


def load_hillstrom_csv(
    path: Path,
    *,
    exact_source: str,
    retrieval_date: str,
    license_note: str,
) -> HillstromDataset:
    """Load the known Hillstrom schema without downloading or guessing provenance."""
    _validate_provenance(exact_source, retrieval_date, license_note)
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        rows = tuple(reader)
        columns = tuple(reader.fieldnames or ())
    required = set(_PRIMARY_FEATURES) | {"segment", "visit", "conversion", "spend"}
    missing = sorted(required - set(columns))
    if missing:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom CSV is missing required columns.",
            stage="hillstrom.data.schema",
            context={"missing": missing},
        )
    try:
        actions = tuple(_ACTION_ENCODING[row["segment"].strip()] for row in rows)
    except KeyError as exc:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Hillstrom segment contains an unknown action label.",
            stage="hillstrom.data.actions",
        ) from exc
    raw_features: list[tuple[str, tuple[Any, ...]]] = []
    for name in _PRIMARY_FEATURES:
        if name in _NUMERIC_FEATURES:
            values: tuple[Any, ...] = _parse_numeric_column(rows, name)
        else:
            values = tuple(row[name].strip() for row in rows)
        raw_features.append((name, values))
    payload = {
        "feature_columns": tuple(raw_features),
        "actions": actions,
        "spend": _parse_numeric_column(rows, "spend"),
        "conversion": _parse_numeric_column(rows, "conversion"),
        "visit": _parse_numeric_column(rows, "visit"),
    }
    dataset_hash = sha256_digest(payload)
    arm_counts = tuple(
        (name, int(np.sum(np.asarray(actions) == index)))
        for index, name in enumerate(HILLSTROM_ACTIONS)
    )
    manifest = HillstromDataManifest(
        dataset_id=f"hillstrom_{dataset_hash.split(':', 1)[1][:16]}",
        dataset_hash=dataset_hash,
        exact_source=exact_source,
        retrieval_date=retrieval_date,
        raw_file_hash=file_sha256(Path(path)),
        row_count=len(rows),
        column_names=columns,
        arm_counts=arm_counts,
        encoding_map=tuple(
            (name, HILLSTROM_ACTIONS[index]) for name, index in _ACTION_ENCODING.items()
        ),
        license_note=license_note,
        source_kind="real_randomized_experiment",
    )
    dataset = HillstromDataset(manifest=manifest, **payload)
    validate_hillstrom_dataset(dataset)
    return dataset


def generate_development_rct(*, n: int = 1800, seed: int = 1729) -> HillstromDataset:
    """Generate a mechanics-only randomized three-arm fixture, not Hillstrom evidence."""
    if n < 90:
        raise ValueError("The development RCT requires at least 90 rows.")
    rng = np.random.default_rng(seed)
    recency = rng.integers(1, 13, size=n).astype(float)
    history = rng.lognormal(mean=5.0, sigma=0.8, size=n)
    mens = rng.integers(0, 2, size=n).astype(float)
    womens = rng.integers(0, 2, size=n).astype(float)
    newbie = rng.binomial(1, 0.35, size=n).astype(float)
    zip_code = rng.choice(np.array(["Urban", "Suburban", "Rural"]), size=n)
    channel = rng.choice(np.array(["Web", "Phone", "Multichannel"]), size=n)
    actions = rng.integers(0, 3, size=n)
    centered_history = np.log1p(history) - np.mean(np.log1p(history))
    baseline = 0.4 + 0.15 * centered_history + 0.2 * newbie
    mens_effect = 0.35 + 0.8 * mens - 0.25 * womens
    womens_effect = 0.30 + 0.8 * womens - 0.25 * mens
    conditional_means = np.column_stack(
        [baseline, baseline + mens_effect, baseline + womens_effect]
    )
    noise = rng.normal(0.0, 1.0, size=n)
    latent = conditional_means[np.arange(n), actions] + noise
    conversion = (latent > 1.3).astype(float)
    visit = (latent > 0.4).astype(float)
    spend = conversion * np.maximum(0.0, 18.0 + 9.0 * latent + rng.normal(0.0, 4.0, n))
    features: tuple[tuple[str, tuple[Any, ...]], ...] = (
        ("recency", tuple(recency)),
        ("history", tuple(history)),
        ("mens", tuple(mens)),
        ("womens", tuple(womens)),
        ("zip_code", tuple(str(value) for value in zip_code)),
        ("newbie", tuple(newbie)),
        ("channel", tuple(str(value) for value in channel)),
    )
    payload = {
        "feature_columns": features,
        "actions": tuple(int(value) for value in actions),
        "spend": tuple(float(value) for value in spend),
        "conversion": tuple(float(value) for value in conversion),
        "visit": tuple(float(value) for value in visit),
    }
    dataset_hash = sha256_digest(payload)
    manifest = HillstromDataManifest(
        dataset_id=f"development_rct_{seed}",
        dataset_hash=dataset_hash,
        exact_source="generated_by_dcfa.generate_development_rct",
        retrieval_date="not_applicable",
        raw_file_hash=sha256_digest(payload),
        row_count=n,
        column_names=tuple(name for name, _ in features)
        + ("segment", "visit", "conversion", "spend"),
        arm_counts=tuple(
            (name, int(np.sum(actions == index))) for index, name in enumerate(HILLSTROM_ACTIONS)
        ),
        encoding_map=tuple((name, str(index)) for index, name in enumerate(HILLSTROM_ACTIONS)),
        license_note="Synthetic fixture generated in-repository; no external data.",
        source_kind="development_synthetic_rct_not_hillstrom",
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
    )
    dataset = HillstromDataset(manifest=manifest, **payload)
    validate_hillstrom_dataset(dataset)
    return dataset


def make_stratified_split(
    dataset: HillstromDataset,
    *,
    seed: int,
) -> SplitManifest:
    validate_hillstrom_dataset(dataset)
    rng = np.random.default_rng(seed)
    train: list[int] = []
    validation: list[int] = []
    test: list[int] = []
    actions = np.asarray(dataset.actions)
    for action in range(len(HILLSTROM_ACTIONS)):
        arm_indices = np.flatnonzero(actions == action)
        arm_indices = rng.permutation(arm_indices)
        train_end = int(np.floor(0.6 * len(arm_indices)))
        validation_end = train_end + int(np.floor(0.2 * len(arm_indices)))
        train.extend(int(value) for value in arm_indices[:train_end])
        validation.extend(int(value) for value in arm_indices[train_end:validation_end])
        test.extend(int(value) for value in arm_indices[validation_end:])
    split = SplitManifest(
        dataset_hash=dataset.manifest.dataset_hash,
        seed=seed,
        stratified_by="randomized_action",
        train_indices=tuple(sorted(train)),
        validation_indices=tuple(sorted(validation)),
        test_indices=tuple(sorted(test)),
    )
    validate_hillstrom_split(split, dataset)
    return split


def validate_split(split: SplitManifest, row_count: int) -> None:
    partitions = [set(split.train_indices), set(split.validation_indices), set(split.test_indices)]
    overlaps = any(
        partitions[left] & partitions[right] for left in range(3) for right in range(left + 1, 3)
    )
    if overlaps:
        raise DCFAError(
            ErrorCode.SPLIT_LEAKAGE,
            "Train, validation, and test indices must be disjoint.",
            stage="hillstrom.split.validation",
        )
    observed = set().union(*partitions)
    if observed != set(range(row_count)):
        raise DCFAError(
            ErrorCode.SPLIT_LEAKAGE,
            "Split indices must cover every row exactly once.",
            stage="hillstrom.split.validation",
        )


def validate_hillstrom_split(split: SplitManifest, dataset: HillstromDataset) -> None:
    """Validate identity, metadata, and actual arm stratification for a frozen split."""
    validate_hillstrom_dataset(dataset)
    validate_split(split, dataset.row_count)
    if split.dataset_hash != dataset.manifest.dataset_hash:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Split manifest does not belong to the immutable Hillstrom dataset.",
            stage="hillstrom.split.validation",
        )
    if split.stratified_by != "randomized_action" or split.ratios != (0.6, 0.2, 0.2):
        raise DCFAError(
            ErrorCode.SPLIT_LEAKAGE,
            "Hillstrom split metadata must freeze randomized-action 60/20/20 stratification.",
            stage="hillstrom.split.validation",
        )
    actions = np.asarray(dataset.actions, dtype=int)
    partitions = (
        np.asarray(split.train_indices, dtype=int),
        np.asarray(split.validation_indices, dtype=int),
        np.asarray(split.test_indices, dtype=int),
    )
    for action in range(len(HILLSTROM_ACTIONS)):
        arm_count = int(np.sum(actions == action))
        expected_counts = (
            int(np.floor(0.6 * arm_count)),
            int(np.floor(0.2 * arm_count)),
            arm_count - int(np.floor(0.6 * arm_count)) - int(np.floor(0.2 * arm_count)),
        )
        observed_counts = tuple(int(np.sum(actions[indices] == action)) for indices in partitions)
        if observed_counts != expected_counts:
            raise DCFAError(
                ErrorCode.SPLIT_LEAKAGE,
                "Hillstrom split is not arm-stratified according to the frozen ratios.",
                stage="hillstrom.split.validation",
                context={
                    "action": HILLSTROM_ACTIONS[action],
                    "expected_counts": list(expected_counts),
                    "observed_counts": list(observed_counts),
                },
            )


def fit_preprocessor(
    dataset: HillstromDataset,
    indices: tuple[int, ...],
    *,
    fit_split: str,
) -> PreprocessingArtifact:
    if not indices or not set(indices) <= set(range(dataset.row_count)):
        raise DCFAError(
            ErrorCode.SPLIT_LEAKAGE,
            "Preprocessor fit indices must be a non-empty in-dataset subset.",
            stage="hillstrom.preprocessing.fit",
        )
    numeric: list[tuple[str, float, float, float]] = []
    categorical: list[tuple[str, tuple[str, ...]]] = []
    encoded_names: list[str] = []
    selected = np.asarray(indices, dtype=int)
    for name, raw_values in dataset.feature_columns:
        if name in _NUMERIC_FEATURES:
            values = np.asarray(raw_values, dtype=float)
            if name == "history":
                values = np.log1p(np.maximum(values, 0.0))
            fit_values = values[selected]
            median = float(np.median(fit_values))
            mean = float(np.mean(fit_values))
            scale = float(np.std(fit_values))
            if scale <= 1e-12:
                scale = 1.0
            numeric.append((name, median, mean, scale))
            encoded_names.append(name)
        else:
            levels = tuple(sorted({str(raw_values[index]) for index in indices}))
            categorical.append((name, levels))
            encoded_names.extend(f"{name}={level}" for level in levels)
    return PreprocessingArtifact(
        fit_split=fit_split,
        fit_indices_hash=sha256_digest(tuple(sorted(indices))),
        raw_feature_names=dataset.feature_names,
        encoded_feature_names=tuple(encoded_names),
        numeric_parameters=tuple(numeric),
        categorical_levels=tuple(categorical),
    )


def transform_features(
    dataset: HillstromDataset,
    indices: tuple[int, ...],
    artifact: PreprocessingArtifact,
) -> np.ndarray:
    if dataset.feature_names != artifact.raw_feature_names:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Dataset feature schema differs from the frozen preprocessor.",
            stage="hillstrom.preprocessing.transform",
        )
    columns = dict(dataset.feature_columns)
    transformed: list[np.ndarray] = []
    selected = np.asarray(indices, dtype=int)
    for name, median, mean, scale in artifact.numeric_parameters:
        values = np.asarray(columns[name], dtype=float)
        if name == "history":
            values = np.log1p(np.maximum(values, 0.0))
        values = np.where(np.isfinite(values), values, median)
        transformed.append(((values[selected] - mean) / scale).reshape(-1, 1))
    for name, levels in artifact.categorical_levels:
        values = np.asarray(columns[name], dtype=str)[selected]
        transformed.extend((values == level).astype(float).reshape(-1, 1) for level in levels)
    return np.hstack(transformed) if transformed else np.empty((len(indices), 0), dtype=float)


class TestOutcomeGate:
    """The only evaluation-tool path to test outcomes."""

    def __init__(self, dataset: HillstromDataset, split: SplitManifest) -> None:
        validate_hillstrom_split(split, dataset)
        self._dataset = dataset
        self._split = split
        self._accessed_by_policy_id: str | None = None

    @property
    def test_outcomes_accessed(self) -> bool:
        return self._accessed_by_policy_id is not None

    def test_features(self, preprocessing: PreprocessingArtifact) -> np.ndarray:
        return transform_features(self._dataset, self._split.test_indices, preprocessing)

    def _authorize(
        self,
        policy: FrozenPolicyArtifact,
    ) -> np.ndarray:
        if not policy.created_without_test_outcomes:
            raise DCFAError(
                ErrorCode.POLICY_NOT_FROZEN,
                "Policy does not certify creation without test outcomes.",
                stage="hillstrom.test_gate",
            )
        if (
            policy.dataset_hash != self._dataset.manifest.dataset_hash
            or policy.split_manifest_id != self._split.split_manifest_id
        ):
            raise DCFAError(
                ErrorCode.HASH_MISMATCH,
                "Frozen policy does not match the sealed test dataset and split.",
                stage="hillstrom.test_gate",
            )
        if self._accessed_by_policy_id not in {None, policy.policy_id}:
            raise DCFAError(
                ErrorCode.DATA_ACCESS_BLOCKED,
                "Test outcomes were already unlocked for a different frozen policy.",
                stage="hillstrom.test_gate",
            )
        self._accessed_by_policy_id = policy.policy_id
        return np.asarray(self._split.test_indices, dtype=int)

    def unlock(
        self,
        policy: FrozenPolicyArtifact,
    ) -> tuple[np.ndarray, np.ndarray]:
        indices = self._authorize(policy)
        return np.asarray(self._dataset.actions, dtype=int)[indices], np.asarray(
            self._dataset.spend, dtype=float
        )[indices]

    def unlock_named_outcome(
        self,
        policy: FrozenPolicyArtifact,
        outcome: str,
    ) -> np.ndarray:
        indices = self._authorize(policy)
        if outcome not in {"spend", "conversion", "visit"}:
            raise DCFAError(
                ErrorCode.INVALID_SPECIFICATION,
                "Unknown Hillstrom outcome requested from the sealed test gate.",
                stage="hillstrom.test_gate",
            )
        return np.asarray(getattr(self._dataset, outcome), dtype=float)[indices]
