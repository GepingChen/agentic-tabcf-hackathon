"""Development-only managed TabPFN Client backend.

The official client sends training and prediction data to Prior Labs.  This
module is deliberately separate from the local, hash-locked TabPFN backend and
does not import ``tabpfn_client`` until the managed path is explicitly used.
"""

from __future__ import annotations

import importlib
import importlib.metadata
from dataclasses import dataclass
from typing import Any

import numpy as np

from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import BackendError, DCFAError, ErrorCode
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.schemas import AnalysisSpecification, BackendManifest
from dcfa.tabcf_iv.backend import (
    UPSTREAM_TABCF_COMMIT,
    DistributionModel,
    MeanModel,
    _as_feature_matrix,
    _as_target,
    _distribution_eval_matrix,
)

MANAGED_CLIENT_PROTOCOL_VERSION = "tabpfn_client_managed_demo_v3"
MANAGED_CLIENT_VERSION = "0.6.1"
MANAGED_SERVICE_PACKAGE_VERSION = "9.0.0"
MANAGED_MODEL_PATH = "v3.5_default"
MANAGED_N_ESTIMATORS = 1
MANAGED_MAX_TRAIN_ROWS = 256
MANAGED_MAX_PREDICT_ROWS = 400
MANAGED_SERVICE_ENDPOINT = "https://api.priorlabs.ai"

MANAGED_BACKEND_PARAMETERS: tuple[tuple[str, str], ...] = (
    ("access_mode", "managed_client"),
    ("managed_protocol_version", MANAGED_CLIENT_PROTOCOL_VERSION),
    ("client_version", MANAGED_CLIENT_VERSION),
    ("expected_service_package_version", MANAGED_SERVICE_PACKAGE_VERSION),
    ("model_path", MANAGED_MODEL_PATH),
    ("n_estimators", str(MANAGED_N_ESTIMATORS)),
    ("thinking_mode", "false"),
)


def _numpy_bar_distribution_cdf(
    borders: np.ndarray,
    logits: np.ndarray,
    evaluation_values: np.ndarray,
) -> np.ndarray:
    """Match TabPFN 9.0.0 ``BarDistribution.cdf`` without importing Torch.

    FullSupportBarDistribution inherits this CDF; its mean has separate tail
    handling and is obtained from the service's mean prediction, not this grid.
    """
    border_values = np.asarray(borders, dtype=float)
    transported_logits = np.asarray(logits, dtype=float)
    evaluation = np.asarray(evaluation_values, dtype=float)
    if border_values.ndim != 1 or border_values.size < 2:
        raise ValueError("Managed TabPFN borders must be a one-dimensional bin grid.")
    if transported_logits.ndim != 2 or transported_logits.shape[1] != border_values.size - 1:
        raise ValueError("Managed TabPFN logits do not match the returned borders.")
    if evaluation.ndim != 2 or evaluation.shape[0] != transported_logits.shape[0]:
        raise ValueError("Managed TabPFN CDF evaluation rows do not match logits.")
    if not np.all(np.isfinite(border_values)) or not np.all(np.isfinite(evaluation)):
        raise ValueError("Managed TabPFN borders or evaluation values are non-finite.")
    if np.any(np.isposinf(transported_logits)):
        raise ValueError("Managed TabPFN logits contain positive infinity.")

    # TabPFN 8.3.0 returns log(probabilities), so exact zero probabilities are
    # ``-inf``. The service JSON represents those values as null and client
    # 0.3.3 materializes null as NaN. Restore only that transport case, then
    # require at least one genuine finite logit in every row.
    logit_values = np.where(np.isnan(transported_logits), -np.inf, transported_logits)
    finite_by_row = np.any(np.isfinite(logit_values), axis=1)
    if not np.all(finite_by_row):
        raise ValueError("Managed TabPFN logits contain a row with no finite probability mass.")
    bucket_widths = np.diff(border_values)
    if np.any(bucket_widths < 0.0) or bucket_widths[0] <= 0.0 or bucket_widths[-1] <= 0.0:
        raise ValueError("Managed TabPFN borders violate the full-support ordering contract.")

    shifted_logits = logit_values - np.max(logit_values, axis=1, keepdims=True)
    probabilities = np.exp(shifted_logits)
    probabilities /= np.sum(probabilities, axis=1, keepdims=True)
    bucket_indices = np.searchsorted(border_values, evaluation, side="left") - 1
    bucket_indices[evaluation == border_values[0]] = 0
    bucket_indices[evaluation == border_values[-1]] = border_values.size - 2
    bucket_indices = np.clip(bucket_indices, 0, border_values.size - 2)
    selected_widths = bucket_widths[bucket_indices]
    if np.any(selected_widths <= 0.0):
        raise ValueError("Managed TabPFN CDF evaluation selected a zero-width bin.")

    probability_before_bucket = np.cumsum(probabilities, axis=1) - probabilities
    row_indices = np.arange(logit_values.shape[0])[:, None]
    probability_left = probability_before_bucket[row_indices, bucket_indices]
    share_in_bucket = np.clip(
        (evaluation - border_values[bucket_indices]) / selected_widths,
        0.0,
        1.0,
    )
    result = probability_left + probabilities[row_indices, bucket_indices] * share_in_bucket
    result[evaluation <= border_values[0]] = 0.0
    result[evaluation >= border_values[-1]] = 1.0
    if not np.all(np.isfinite(result)):
        raise ValueError("Managed TabPFN CDF evaluation produced non-finite values.")
    return np.clip(result, 0.0, 1.0)


@dataclass
class TabPFNClientDistributionModel:
    estimator: Any
    backend: TabPFNClientBackend

    def _full_output(self, features: np.ndarray) -> dict[str, Any]:
        matrix = _as_feature_matrix(features)
        self.backend._validate_prediction_size(matrix)
        try:
            output = self.estimator.predict(matrix, output_type="full")
        except DCFAError:
            raise
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "Managed TabPFN distribution prediction failed; no fallback was attempted.",
                stage="managed_client.predict_distribution",
                context={"exception_type": type(exc).__name__},
            ) from exc
        self.backend._record_observation(self.estimator, "full", matrix)
        if not isinstance(output, dict) or not {"borders", "logits"} <= set(output):
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "Managed TabPFN full output did not contain borders and logits.",
                stage="managed_client.predict_distribution",
            )
        return output

    def predict_quantiles(self, features: np.ndarray) -> np.ndarray:
        del features
        raise BackendError(
            ErrorCode.BACKEND_PREDICT_FAILED,
            "Direct managed-client quantiles are not used by the canonical CDF path.",
            stage="managed_client.predict_quantiles",
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
        try:
            result = _numpy_bar_distribution_cdf(
                np.asarray(output["borders"], dtype=float),
                np.asarray(output["logits"], dtype=float),
                evaluation,
            )
        except (TypeError, ValueError) as exc:
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "Managed TabPFN full output could not be evaluated as a CDF.",
                stage="managed_client.predict_cdf",
                context={"exception_type": type(exc).__name__},
            ) from exc
        return result[:, 0] if paired else result


@dataclass
class TabPFNClientMeanModel:
    estimator: Any
    backend: TabPFNClientBackend

    def predict(self, features: np.ndarray) -> np.ndarray:
        matrix = _as_feature_matrix(features)
        self.backend._validate_prediction_size(matrix)
        try:
            result = self.estimator.predict(matrix, output_type="mean")
        except DCFAError:
            raise
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "Managed TabPFN mean prediction failed; no fallback was attempted.",
                stage="managed_client.predict_mean",
                context={"exception_type": type(exc).__name__},
            ) from exc
        self.backend._record_observation(self.estimator, "mean", matrix)
        values = np.asarray(result, dtype=float).reshape(-1)
        if values.shape != (len(matrix),) or not np.all(np.isfinite(values)):
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "Managed TabPFN mean prediction returned malformed values.",
                stage="managed_client.predict_mean",
            )
        return values


class TabPFNClientBackend:
    """Strict, development-only backend for the official Prior Labs client."""

    name = EstimatorBackend.TABPFN
    execution_profile = ExecutionProfile.LOCAL_DEVELOPMENT
    evidence_status = EvidenceStatus.DEVELOPMENT_ONLY

    def __init__(
        self,
        *,
        seed: int,
        regressor_class: Any | None = None,
        client_version: str | None = None,
    ) -> None:
        self.seed = int(seed)
        self.fit_calls = 0
        self.api_prediction_calls = 0
        self._observations: list[tuple[tuple[str, str], ...]] = []
        self._regressor_class = regressor_class
        self.client_version = client_version or self._installed_client_version()
        if self.client_version != MANAGED_CLIENT_VERSION:
            raise BackendError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "The managed development profile requires the frozen tabpfn-client version.",
                stage="managed_client.version",
                context={
                    "expected": MANAGED_CLIENT_VERSION,
                    "observed": self.client_version,
                },
            )

    @staticmethod
    def _installed_client_version() -> str:
        try:
            return importlib.metadata.version("tabpfn-client")
        except importlib.metadata.PackageNotFoundError as exc:
            raise BackendError(
                ErrorCode.BACKEND_IMPORT_FAILED,
                "tabpfn-client is not installed; no fallback was attempted.",
                stage="managed_client.import",
            ) from exc

    @classmethod
    def from_specification(
        cls,
        specification: AnalysisSpecification,
        *,
        regressor_class: Any | None = None,
        client_version: str | None = None,
    ) -> TabPFNClientBackend:
        if tuple(specification.backend_parameters) != MANAGED_BACKEND_PARAMETERS:
            raise DCFAError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Managed TabPFN execution requires the exact frozen smoke parameters.",
                stage="managed_client.specification",
            )
        return cls(
            seed=specification.seed,
            regressor_class=regressor_class,
            client_version=client_version,
        )

    def _load_regressor_class(self) -> Any:
        if self._regressor_class is not None:
            return self._regressor_class
        try:
            module = importlib.import_module("tabpfn_client")
            return module.TabPFNRegressor
        except DCFAError:
            raise
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_IMPORT_FAILED,
                "tabpfn-client could not be imported; no fallback was attempted.",
                stage="managed_client.import",
                context={"exception_type": type(exc).__name__},
            ) from exc

    def _new_estimator(self) -> Any:
        regressor_class = self._load_regressor_class()
        try:
            return regressor_class(
                model_path=MANAGED_MODEL_PATH,
                n_estimators=MANAGED_N_ESTIMATORS,
                random_state=self.seed,
                ignore_pretraining_limits=False,
                thinking_mode=False,
            )
        except DCFAError:
            raise
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_LOAD_FAILED,
                "Managed TabPFN regressor initialization failed; no fallback was attempted.",
                stage="managed_client.load",
                context={"exception_type": type(exc).__name__},
            ) from exc

    @staticmethod
    def _validate_training_size(matrix: np.ndarray) -> None:
        if len(matrix) > MANAGED_MAX_TRAIN_ROWS:
            raise BackendError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Managed TabPFN training rows exceed the frozen development limit.",
                stage="managed_client.size_gate",
                context={"maximum": MANAGED_MAX_TRAIN_ROWS, "observed": len(matrix)},
            )

    @staticmethod
    def _validate_prediction_size(matrix: np.ndarray) -> None:
        if len(matrix) > MANAGED_MAX_PREDICT_ROWS:
            raise BackendError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Managed TabPFN prediction rows exceed the frozen development limit.",
                stage="managed_client.size_gate",
                context={"maximum": MANAGED_MAX_PREDICT_ROWS, "observed": len(matrix)},
            )

    def _fit_estimator(self, features: np.ndarray, target: np.ndarray) -> Any:
        matrix = _as_feature_matrix(features)
        values = _as_target(target, len(matrix))
        self._validate_training_size(matrix)
        estimator = self._new_estimator()
        try:
            estimator.fit(matrix, values)
        except DCFAError:
            raise
        except Exception as exc:
            raise BackendError(
                ErrorCode.BACKEND_FIT_FAILED,
                "Managed TabPFN fitting failed; no fallback was attempted.",
                stage="managed_client.fit",
                context={"exception_type": type(exc).__name__},
            ) from exc
        self.fit_calls += 1
        return estimator

    def _record_observation(
        self,
        estimator: Any,
        output_type: str,
        matrix: np.ndarray,
    ) -> None:
        metadata = getattr(estimator, "_last_meta", None)
        if not isinstance(metadata, dict):
            raise BackendError(
                ErrorCode.BACKEND_PREDICT_FAILED,
                "Managed TabPFN response did not expose service metadata.",
                stage="managed_client.metadata",
            )
        observed_version = str(metadata.get("package_version", ""))
        if observed_version != MANAGED_SERVICE_PACKAGE_VERSION:
            raise BackendError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "Managed TabPFN service package version differs from the frozen smoke profile.",
                stage="managed_client.metadata",
                context={
                    "expected": MANAGED_SERVICE_PACKAGE_VERSION,
                    "observed": observed_version or "missing",
                },
            )
        billing_version = metadata.get("billing_model_version")
        if billing_version is not None and billing_version != "v3.5":
            raise BackendError(
                ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
                "The managed service returned an unexpected model version.",
                stage="managed_client.model_version",
            )
        config = metadata.get("tabpfn_config") or {}
        self.api_prediction_calls += 1
        trace_id = str(getattr(estimator, "_last_trace_id", "unavailable"))
        self._observations.append(
            (
                ("output_type", output_type),
                ("rows", str(len(matrix))),
                ("columns", str(matrix.shape[1])),
                ("service_package_version", observed_version),
                ("model_path", str(config.get("model_path", "unavailable"))),
                (
                    "billing_model_version",
                    str(metadata.get("billing_model_version", "unavailable")),
                ),
                ("n_estimators", str(metadata.get("n_estimators", "unavailable"))),
                ("trace_id", trace_id),
            )
        )

    @property
    def audit_details(self) -> tuple[tuple[str, str], ...]:
        details: list[tuple[str, str]] = [
            ("managed_protocol_version", MANAGED_CLIENT_PROTOCOL_VERSION),
            ("api_prediction_calls", str(self.api_prediction_calls)),
        ]
        for index, observation in enumerate(self._observations, start=1):
            details.extend((f"request_{index}_{name}", value) for name, value in observation)
        return tuple(details)

    @property
    def manifest(self) -> BackendManifest:
        return BackendManifest(
            track=Track.TABCF_IV,
            estimator_backend=self.name,
            execution_profile=self.execution_profile,
            evidence_status=self.evidence_status,
            model_class_mean="tabpfn_client.TabPFNRegressor(output_type='mean')",
            model_class_distribution="tabpfn_client.TabPFNRegressor(output_type='full')",
            parameters=(
                *MANAGED_BACKEND_PARAMETERS,
                ("service_endpoint", MANAGED_SERVICE_ENDPOINT),
                ("max_train_rows", MANAGED_MAX_TRAIN_ROWS),
                ("max_predict_rows", MANAGED_MAX_PREDICT_ROWS),
            ),
            quantile_grid=(),
            seed=self.seed,
            package_versions=(("tabpfn-client", self.client_version),),
            cdf_rule=(
                "NumPy parity with TabPFN 9.0.0 BarDistribution.cdf over managed borders and "
                "logits; client JSON null logits restore exact zero probability"
            ),
            quantile_monotonicity_rule=(
                "canonical DCFA row-wise clip and cumulative maximum after V integration"
            ),
            upstream_source_commit=UPSTREAM_TABCF_COMMIT,
            dcfa_source_tree_hash=dcfa_source_tree_hash(),
            model_artifact_hash="managed_service_checkpoint_not_locally_available",
            runtime_image_digest="managed_service_runtime_not_locally_available",
        )

    def fit_distribution(self, features: np.ndarray, target: np.ndarray) -> DistributionModel:
        return TabPFNClientDistributionModel(self._fit_estimator(features, target), self)

    def fit_mean(self, features: np.ndarray, target: np.ndarray) -> MeanModel:
        return TabPFNClientMeanModel(self._fit_estimator(features, target), self)
