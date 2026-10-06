"""Explicit statistical-backend contracts for the TabCF IV adapter.

The local sklearn implementation is an engineering fallback, not TabCF. This
module intentionally has no top-level torch or tabpfn import.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from dcfa.canonical import file_sha256, is_sha256_digest
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import BackendError, DCFAError, ErrorCode
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.schemas import BackendManifest

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

FALLBACK_QUANTILE_GRID = (0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 0.95, 0.98)
FALLBACK_PARAMETERS: tuple[tuple[str, Any], ...] = (
    ("early_stopping", False),
    ("l2_regularization", 1.0),
    ("learning_rate", 0.05),
    ("max_iter", 140),
    ("max_leaf_nodes", 15),
    ("min_samples_leaf", 12),
)
UPSTREAM_TABCF_COMMIT = "76e0d3eb9e97cebca381d1540db0333c1ef1016e"


class DistributionModel(Protocol):
    def predict_quantiles(self, features: np.ndarray) -> np.ndarray: ...

    def cdf(
        self,
        features: np.ndarray,
        values: np.ndarray | float,
        *,
        paired: bool,
    ) -> np.ndarray: ...


class MeanModel(Protocol):
    def predict(self, features: np.ndarray) -> np.ndarray: ...


class StatisticalBackend(Protocol):
    name: EstimatorBackend
    execution_profile: ExecutionProfile
    evidence_status: EvidenceStatus
    fit_calls: int

    @property
    def manifest(self) -> BackendManifest: ...

    def fit_distribution(self, features: np.ndarray, target: np.ndarray) -> DistributionModel: ...

    def fit_mean(self, features: np.ndarray, target: np.ndarray) -> MeanModel: ...


def _as_feature_matrix(features: np.ndarray) -> np.ndarray:
    matrix = np.asarray(features, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError(f"Expected a non-empty 2D feature matrix, got {matrix.shape}.")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Feature matrix contains non-finite values.")
    return matrix


def _as_target(target: np.ndarray, n_rows: int) -> np.ndarray:
    values = np.asarray(target, dtype=float).reshape(-1)
    if len(values) != n_rows:
        raise ValueError(f"Feature/target length mismatch: {n_rows} vs {len(values)}.")
    if not np.all(np.isfinite(values)):
        raise ValueError("Target contains non-finite values.")
    return values


def _distribution_eval_matrix(
    values: np.ndarray | float,
    *,
    n_rows: int,
    paired: bool,
) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if paired:
        paired_values = array.reshape(-1)
        if len(paired_values) != n_rows:
            raise ValueError(
                f"Paired CDF evaluation requires {n_rows} values; got {len(paired_values)}."
            )
        return paired_values.reshape(n_rows, 1)
    shared = array.reshape(-1)
    if shared.size == 0:
        raise ValueError("CDF evaluation grid must not be empty.")
    return np.tile(shared.reshape(1, -1), (n_rows, 1))


def _cdf_from_quantile_rows(
    quantile_values: np.ndarray,
    quantile_levels: tuple[float, ...],
    evaluation_values: np.ndarray,
) -> np.ndarray:
    """Build a CDF by fixed linear interpolation over monotone quantile knots."""
    output = np.empty_like(evaluation_values, dtype=float)
    levels = np.asarray(quantile_levels, dtype=float)
    for row_index, (knots, row_values) in enumerate(
        zip(quantile_values, evaluation_values, strict=True)
    ):
        unique_knots, inverse = np.unique(knots, return_inverse=True)
        unique_levels = np.zeros(len(unique_knots), dtype=float)
        for knot_index in range(len(unique_knots)):
            unique_levels[knot_index] = float(np.max(levels[inverse == knot_index]))
        if len(unique_knots) == 1:
            output[row_index] = np.where(row_values < unique_knots[0], 0.0, 1.0)
        else:
            output[row_index] = np.interp(
                row_values,
                unique_knots,
                unique_levels,
                left=0.0,
                right=1.0,
            )
    return np.clip(output, 0.0, 1.0)


@dataclass
class SklearnQuantileDistributionModel:
    models: tuple[HistGradientBoostingRegressor, ...]
    quantile_grid: tuple[float, ...]

    def predict_quantiles(self, features: np.ndarray) -> np.ndarray:
        matrix = _as_feature_matrix(features)
        raw = np.column_stack([model.predict(matrix) for model in self.models])
        return np.maximum.accumulate(np.asarray(raw, dtype=float), axis=1)

    def cdf(
        self,
        features: np.ndarray,
        values: np.ndarray | float,
        *,
        paired: bool,
    ) -> np.ndarray:
        matrix = _as_feature_matrix(features)
        evaluation = _distribution_eval_matrix(values, n_rows=len(matrix), paired=paired)
        quantiles = self.predict_quantiles(matrix)
        result = _cdf_from_quantile_rows(quantiles, self.quantile_grid, evaluation)
        return result[:, 0] if paired else result


@dataclass
class SklearnMeanModel:
    model: HistGradientBoostingRegressor

    def predict(self, features: np.ndarray) -> np.ndarray:
        return np.asarray(self.model.predict(_as_feature_matrix(features)), dtype=float).reshape(-1)


class SklearnQuantileBackend:
    """Deterministic CPU engineering backend, explicitly ineligible for Track T release."""

    name = EstimatorBackend.SKLEARN_QUANTILE_FALLBACK
    execution_profile = ExecutionProfile.LOCAL_DEVELOPMENT
    evidence_status = EvidenceStatus.DEVELOPMENT_ONLY

    def __init__(
        self,
        *,
        seed: int,
        quantile_grid: tuple[float, ...] = FALLBACK_QUANTILE_GRID,
    ) -> None:
        if tuple(sorted(quantile_grid)) != tuple(quantile_grid):
            raise ValueError("quantile_grid must be sorted in increasing order.")
        if not quantile_grid or min(quantile_grid) <= 0.0 or max(quantile_grid) >= 1.0:
            raise ValueError("quantile_grid values must be strictly inside (0, 1).")
        self.seed = int(seed)
        self.quantile_grid = tuple(float(level) for level in quantile_grid)
        self.fit_calls = 0

    def _model_kwargs(self) -> dict[str, Any]:
        return {**dict(FALLBACK_PARAMETERS), "random_state": self.seed}

    @property
    def manifest(self) -> BackendManifest:
        return BackendManifest(
            track=Track.TABCF_IV,
            estimator_backend=self.name,
            execution_profile=self.execution_profile,
            evidence_status=self.evidence_status,
            model_class_mean="sklearn.ensemble.HistGradientBoostingRegressor(loss='squared_error')",
            model_class_distribution=(
                "sklearn.ensemble.HistGradientBoostingRegressor(loss='quantile')"
            ),
            parameters=(*FALLBACK_PARAMETERS, ("process_thread_limit", 1)),
            quantile_grid=self.quantile_grid,
            seed=self.seed,
            package_versions=(("scikit-learn", importlib.metadata.version("scikit-learn")),),
            cdf_rule=(
                "row-wise linear interpolation of fixed quantile knots; left tail=0; "
                "right tail=1; duplicate knots use the largest quantile level"
            ),
            quantile_monotonicity_rule="row-wise cumulative maximum in increasing quantile level",
            upstream_source_commit=UPSTREAM_TABCF_COMMIT,
            dcfa_source_tree_hash=dcfa_source_tree_hash(),
        )

    def fit_distribution(self, features: np.ndarray, target: np.ndarray) -> DistributionModel:
        matrix = _as_feature_matrix(features)
        values = _as_target(target, len(matrix))
        fitted: list[HistGradientBoostingRegressor] = []
        try:
            for level in self.quantile_grid:
                model = HistGradientBoostingRegressor(
                    loss="quantile",
                    quantile=level,
                    **self._model_kwargs(),
                )
                model.fit(matrix, values)
                fitted.append(model)
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_FIT_FAILED,
                "The explicitly selected sklearn distribution backend failed to fit.",
                stage="backend.fit_distribution",
                context={"backend": self.name.value, "exception_type": type(exc).__name__},
            ) from exc
        self.fit_calls += 1
        return SklearnQuantileDistributionModel(tuple(fitted), self.quantile_grid)

    def fit_mean(self, features: np.ndarray, target: np.ndarray) -> MeanModel:
        matrix = _as_feature_matrix(features)
        values = _as_target(target, len(matrix))
        try:
            model = HistGradientBoostingRegressor(loss="squared_error", **self._model_kwargs())
            model.fit(matrix, values)
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_FIT_FAILED,
                "The explicitly selected sklearn mean backend failed to fit.",
                stage="backend.fit_mean",
                context={"backend": self.name.value, "exception_type": type(exc).__name__},
            ) from exc
        self.fit_calls += 1
        return SklearnMeanModel(model)


class TabPFNDistributionModel:
    """Thin adapter over the inspected upstream TabPFN predictive-distribution API."""

    def __init__(self, estimator: Any, torch_module: Any) -> None:
        self.estimator = estimator
        self.torch = torch_module

    def _full_output(self, features: np.ndarray) -> dict[str, Any]:
        try:
            result = self.estimator.predict(_as_feature_matrix(features), output_type="full")
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "TabPFN predictive-distribution inference failed; no fallback was attempted.",
                stage="backend.predict_distribution",
                context={
                    "backend": EstimatorBackend.TABPFN.value,
                    "exception_type": type(exc).__name__,
                },
            ) from exc
        if not isinstance(result, dict) or "criterion" not in result or "logits" not in result:
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "TabPFN full output did not contain criterion and logits.",
                stage="backend.predict_distribution",
                context={"backend": EstimatorBackend.TABPFN.value},
            )
        return result

    def predict_quantiles(self, features: np.ndarray) -> np.ndarray:
        raise BackendError(
            ErrorCode.BACKEND_PREDICT_FAILED,
            "Direct TabPFN quantile prediction is not used by the canonical CDF path.",
            stage="backend.predict_quantiles",
        )

    def cdf(
        self,
        features: np.ndarray,
        values: np.ndarray | float,
        *,
        paired: bool,
    ) -> np.ndarray:
        matrix = _as_feature_matrix(features)
        evaluation = _distribution_eval_matrix(values, n_rows=len(matrix), paired=paired)
        output = self._full_output(matrix)
        criterion = output["criterion"]
        logits = output["logits"]
        try:
            device = criterion.borders.device
            dtype = criterion.borders.dtype
            logits_tensor = logits if self.torch.is_tensor(logits) else self.torch.as_tensor(logits)
            logits_tensor = logits_tensor.to(device)
            value_tensor = self.torch.as_tensor(evaluation, dtype=dtype, device=device)
            with self.torch.no_grad():
                cdf = criterion.cdf(logits_tensor, value_tensor)
            result = np.asarray(cdf.detach().cpu().numpy(), dtype=float)
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "TabPFN CDF evaluation failed; no fallback was attempted.",
                stage="backend.predict_cdf",
                context={
                    "backend": EstimatorBackend.TABPFN.value,
                    "exception_type": type(exc).__name__,
                },
            ) from exc
        return result[:, 0] if paired else result


@dataclass
class TabPFNMeanModel:
    estimator: Any

    def predict(self, features: np.ndarray) -> np.ndarray:
        try:
            result = self.estimator.predict(_as_feature_matrix(features), output_type="mean")
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "TabPFN mean prediction failed; no fallback was attempted.",
                stage="backend.predict_mean",
                context={
                    "backend": EstimatorBackend.TABPFN.value,
                    "exception_type": type(exc).__name__,
                },
            ) from exc
        return np.asarray(result, dtype=float).reshape(-1)


class TabPFNBackend:
    """Lazy, fail-closed future boundary for the real TabPFN estimator."""

    name = EstimatorBackend.TABPFN

    def __init__(
        self,
        *,
        seed: int,
        execution_profile: ExecutionProfile,
        model_path: str = "auto",
        model_artifact_hash: str = "",
        runtime_image_digest: str = "",
        model_version: str = "unspecified",
        model_repo: str = "unspecified",
        model_revision: str = "unspecified",
        model_filename: str = "unspecified",
        n_estimators: int = 1,
        device: str = "auto",
    ) -> None:
        self.seed = int(seed)
        self.execution_profile = execution_profile
        self.evidence_status = (
            EvidenceStatus.ELIGIBLE_FOR_RELEASE
            if execution_profile is ExecutionProfile.LOCKED_EVALUATION
            else EvidenceStatus.DEVELOPMENT_ONLY
        )
        self.model_path = str(model_path)
        self.model_artifact_hash = str(model_artifact_hash)
        self.runtime_image_digest = str(runtime_image_digest)
        self.model_version = str(model_version)
        self.model_repo = str(model_repo)
        self.model_revision = str(model_revision)
        self.model_filename = str(model_filename)
        self.n_estimators = int(n_estimators)
        self.device = str(device)
        self.fit_calls = 0

    def _validate_model_artifact(self) -> None:
        if not self.model_artifact_hash:
            return
        if self.model_path.strip().lower() == "auto":
            raise BackendError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "A hashed TabPFN model requires an explicit model path.",
                stage="backend.model_artifact",
            )
        model_path = Path(self.model_path)
        if not model_path.is_file() or file_sha256(model_path) != self.model_artifact_hash:
            raise BackendError(
                ErrorCode.HASH_MISMATCH,
                "TabPFN model artifact is missing or does not match its frozen hash.",
                stage="backend.model_artifact",
                context={"model_path": self.model_path},
            )

    def _validate_locked_runtime(self) -> None:
        if self.execution_profile is not ExecutionProfile.LOCKED_EVALUATION:
            self._validate_model_artifact()
            return
        missing: list[str] = []
        if self.model_path.strip().lower() == "auto":
            missing.append("explicit_model_path")
        if not is_sha256_digest(self.model_artifact_hash):
            missing.append("model_artifact_hash")
        if not is_sha256_digest(self.runtime_image_digest):
            missing.append("runtime_image_digest")
        if missing:
            raise BackendError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Locked TabPFN execution requires an explicit hashed model and image digest.",
                stage="backend.locked_runtime",
                context={"missing": missing},
            )
        observed_runtime_digest = os.environ.get("DCFA_RUNTIME_IMAGE_DIGEST", "")
        if observed_runtime_digest != self.runtime_image_digest:
            raise BackendError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Current host does not match the frozen runtime image digest.",
                stage="backend.locked_runtime",
                context={
                    "expected": self.runtime_image_digest,
                    "observed": observed_runtime_digest or "unset",
                },
            )
        self._validate_model_artifact()

    def _load_classes(self) -> tuple[Any, Any]:
        try:
            torch_module = importlib.import_module("torch")
            try:
                regressor_module = importlib.import_module("tabpfn.regressor")
                regressor_class = regressor_module.TabPFNRegressor
            except (ImportError, AttributeError):
                tabpfn_module = importlib.import_module("tabpfn")
                regressor_class = tabpfn_module.TabPFNRegressor
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_IMPORT_FAILED,
                "TabPFN or torch could not be imported; no fallback was attempted.",
                stage="backend.import",
                context={"backend": self.name.value, "exception_type": type(exc).__name__},
            ) from exc
        return regressor_class, torch_module

    def _new_estimator(self) -> tuple[Any, Any]:
        self._validate_locked_runtime()
        regressor_class, torch_module = self._load_classes()
        kwargs: dict[str, Any] = {
            "random_state": self.seed,
            "ignore_pretraining_limits": True,
            "n_estimators": self.n_estimators,
            "device": self.device,
        }
        if self.model_path.strip().lower() != "auto":
            kwargs["model_path"] = self.model_path
        try:
            return regressor_class(**kwargs), torch_module
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_LOAD_FAILED,
                "TabPFN regressor initialization failed; no fallback was attempted.",
                stage="backend.load",
                context={"backend": self.name.value, "exception_type": type(exc).__name__},
            ) from exc

    @property
    def manifest(self) -> BackendManifest:
        versions: list[tuple[str, str]] = []
        for package in ("tabpfn", "torch"):
            try:
                versions.append((package, importlib.metadata.version(package)))
            except importlib.metadata.PackageNotFoundError:
                versions.append((package, "not-installed"))
        return BackendManifest(
            track=Track.TABCF_IV,
            estimator_backend=self.name,
            execution_profile=self.execution_profile,
            evidence_status=self.evidence_status,
            model_class_mean="tabpfn.TabPFNRegressor(output_type='mean')",
            model_class_distribution="tabpfn.TabPFNRegressor(output_type='full')",
            parameters=(
                ("device", self.device),
                ("ignore_pretraining_limits", True),
                ("model_filename", self.model_filename),
                ("model_path", self.model_path),
                ("model_repo", self.model_repo),
                ("model_revision", self.model_revision),
                ("model_version", self.model_version),
                ("n_estimators", self.n_estimators),
            ),
            quantile_grid=(),
            seed=self.seed,
            package_versions=tuple(versions),
            cdf_rule="criterion.cdf(logits, values) using inspected upstream full output API",
            quantile_monotonicity_rule=(
                "canonical DCFA row-wise clip and cumulative maximum after V integration"
            ),
            upstream_source_commit=UPSTREAM_TABCF_COMMIT,
            dcfa_source_tree_hash=dcfa_source_tree_hash(),
            model_artifact_hash=(self.model_artifact_hash or "missing"),
            runtime_image_digest=(self.runtime_image_digest or "missing"),
        )

    def _fit_estimator(self, features: np.ndarray, target: np.ndarray) -> tuple[Any, Any]:
        matrix = _as_feature_matrix(features)
        values = _as_target(target, len(matrix))
        estimator, torch_module = self._new_estimator()
        try:
            estimator.fit(matrix, values)
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_FIT_FAILED,
                "TabPFN fitting failed; no fallback was attempted.",
                stage="backend.fit",
                context={"backend": self.name.value, "exception_type": type(exc).__name__},
            ) from exc
        self.fit_calls += 1
        return estimator, torch_module

    def fit_distribution(self, features: np.ndarray, target: np.ndarray) -> TabPFNDistributionModel:
        estimator, torch_module = self._fit_estimator(features, target)
        model = TabPFNDistributionModel(estimator, torch_module)
        sample_count = min(4, len(_as_feature_matrix(features)))
        _ = model.cdf(
            _as_feature_matrix(features)[:sample_count],
            np.asarray(target, dtype=float)[:sample_count],
            paired=True,
        )
        return model

    def fit_mean(self, features: np.ndarray, target: np.ndarray) -> MeanModel:
        estimator, _ = self._fit_estimator(features, target)
        return TabPFNMeanModel(estimator)

    def fit_mean_distribution(
        self, features: np.ndarray, target: np.ndarray
    ) -> tuple[MeanModel, DistributionModel]:
        """Use the same fitted local regressor for both Stage 2 output types."""
        distribution = self.fit_distribution(features, target)
        return TabPFNMeanModel(distribution.estimator), distribution


def make_backend(
    backend: EstimatorBackend,
    *,
    execution_profile: ExecutionProfile,
    seed: int,
    model_path: str = "auto",
    model_artifact_hash: str = "",
    runtime_image_digest: str = "",
) -> StatisticalBackend:
    if backend is EstimatorBackend.SKLEARN_QUANTILE_FALLBACK:
        if execution_profile is not ExecutionProfile.LOCAL_DEVELOPMENT:
            raise DCFAError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "sklearn_quantile_fallback is allowed only in local_development.",
                stage="backend.selection",
            )
        return SklearnQuantileBackend(seed=seed)
    if backend is EstimatorBackend.TABPFN:
        return TabPFNBackend(
            seed=seed,
            execution_profile=execution_profile,
            model_path=model_path,
            model_artifact_hash=model_artifact_hash,
            runtime_image_digest=runtime_image_digest,
        )
    raise DCFAError(
        ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
        f"Backend {backend.value} is not allowed for scientific execution.",
        stage="backend.selection",
    )
