"""Frozen synthetic agent smoke path for the official TabPFN Client."""

from __future__ import annotations

import importlib
import importlib.metadata
import stat
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from dcfa.agent.compiler import CompilationRequest
from dcfa.agent.runtime import AgentResponse, CausalAgentRuntime
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile
from dcfa.errors import DCFAError, ErrorCode
from dcfa.schemas import AnalysisSpecification, DatasetManifest, QueryResult
from dcfa.tabcf_iv.development_dgp import generate_development_iv
from dcfa.tabcf_iv.managed_client import (
    MANAGED_BACKEND_PARAMETERS,
    MANAGED_CLIENT_VERSION,
    TabPFNClientBackend,
)
from dcfa.tabcf_iv.pipeline import AnalysisRun, TabCFAnalysisEngine

MANAGED_SMOKE_SEED = 20260812
MANAGED_SMOKE_ROWS = 128


@dataclass(frozen=True)
class ManagedAgentSmokeResult:
    response: AgentResponse
    run: AnalysisRun | None
    usage_before: str
    usage_after: str
    api_prediction_calls: int


class _OutputBoundAnalysisTool:
    def __init__(self, engine: TabCFAnalysisEngine, output_dir: Path) -> None:
        self.engine = engine
        self.output_dir = output_dir
        self.last_run: AnalysisRun | None = None

    def analyze(
        self,
        data: dict[str, np.ndarray],
        specification: AnalysisSpecification,
        dataset_manifest: DatasetManifest,
        *,
        output_dir: Any = None,
    ) -> AnalysisRun:
        if output_dir is not None:
            raise ValueError("The managed smoke output directory is fixed by the caller.")
        self.last_run = self.engine.analyze(
            data,
            specification,
            dataset_manifest,
            output_dir=self.output_dir,
        )
        return self.last_run

    def follow_up(
        self,
        specification: AnalysisSpecification,
        query_id: str,
    ) -> QueryResult:
        return self.engine.follow_up(specification, query_id)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def read_managed_token_file(token_file: Path) -> str:
    try:
        path = token_file.expanduser().resolve(strict=True)
    except OSError as exc:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The managed TabPFN token file is unavailable.",
            stage="managed_client.credentials",
            context={"exception_type": type(exc).__name__},
        ) from exc
    repository = _repository_root()
    if path == repository or repository in path.parents:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The managed TabPFN token file must remain outside the repository.",
            stage="managed_client.credentials",
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The managed TabPFN token file must not be accessible by group or others.",
            stage="managed_client.credentials",
            context={"mode": oct(mode)},
        )
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The managed TabPFN token file could not be read.",
            stage="managed_client.credentials",
            context={"exception_type": type(exc).__name__},
        ) from exc
    if not token.startswith("tabpfn_sk_") or len(token) < 24:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The managed TabPFN token file does not contain a recognized API key.",
            stage="managed_client.credentials",
        )
    return token


def load_managed_client_module() -> Any:
    try:
        version = importlib.metadata.version("tabpfn-client")
        module = importlib.import_module("tabpfn_client")
    except Exception as exc:
        raise DCFAError(
            ErrorCode.BACKEND_IMPORT_FAILED,
            "The frozen tabpfn-client dependency is unavailable.",
            stage="managed_client.import",
            context={"exception_type": type(exc).__name__},
        ) from exc
    if version != MANAGED_CLIENT_VERSION:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "The installed tabpfn-client version does not match the frozen smoke profile.",
            stage="managed_client.version",
            context={"expected": MANAGED_CLIENT_VERSION, "observed": version},
        )
    return module


def run_managed_agent_smoke(
    *,
    token_file: Path,
    output_dir: Path,
    client_module: Any | None = None,
    client_version: str | None = None,
) -> ManagedAgentSmokeResult:
    """Run one typed-agent tool call over a fixed synthetic TabPFN-IV scenario."""
    token = read_managed_token_file(token_file)
    client = client_module or load_managed_client_module()
    observed_client_version = client_version or importlib.metadata.version("tabpfn-client")
    if observed_client_version != MANAGED_CLIENT_VERSION:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "The managed client version is not frozen correctly.",
            stage="managed_client.version",
            context={
                "expected": MANAGED_CLIENT_VERSION,
                "observed": observed_client_version,
            },
        )

    try:
        client.set_access_token(token)
        del token
        usage_before = str(client.get_api_usage())

        dataset = generate_development_iv(
            n=MANAGED_SMOKE_ROWS,
            seed=MANAGED_SMOKE_SEED,
            instrument_strength=1.6,
        )
        manifest = replace(dataset.manifest, estimator_backend=EstimatorBackend.TABPFN)
        x_grid = tuple(
            float(value) for value in np.quantile(dataset.columns["X"], [0.1, 0.3, 0.5, 0.7, 0.9])
        )
        request = CompilationRequest(
            dataset_hash=manifest.dataset_hash,
            outcome="Y",
            treatment="X",
            instrument="Z",
            objective="quantile_contrast",
            intervention_grid=x_grid,
            x=x_grid[3],
            comparison_x=x_grid[1],
            level=0.5,
            units="Y_units",
            confirmed_by_user=True,
            execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
            estimator_backend=EstimatorBackend.TABPFN,
            evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
            backend_parameters=MANAGED_BACKEND_PARAMETERS,
            seed=MANAGED_SMOKE_SEED,
        )

        created_backends: list[TabPFNClientBackend] = []

        def backend_factory(specification: AnalysisSpecification) -> TabPFNClientBackend:
            backend = TabPFNClientBackend.from_specification(
                specification,
                regressor_class=client.TabPFNRegressor,
                client_version=observed_client_version,
            )
            created_backends.append(backend)
            return backend

        engine = TabCFAnalysisEngine(backend_factory=backend_factory)
        tool = _OutputBoundAnalysisTool(engine, output_dir)
        response = CausalAgentRuntime(analysis_tool=tool).execute(
            request,
            dataset.columns,
            manifest,
        )
        usage_after = str(client.get_api_usage())
        prediction_calls = sum(backend.api_prediction_calls for backend in created_backends)
        return ManagedAgentSmokeResult(
            response=response,
            run=tool.last_run,
            usage_before=usage_before,
            usage_after=usage_after,
            api_prediction_calls=prediction_calls,
        )
    finally:
        client.reset()
