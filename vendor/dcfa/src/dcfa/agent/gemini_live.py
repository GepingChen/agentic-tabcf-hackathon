"""One-call Gemini compiler smoke over the deterministic Track A runtime."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import stat
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from dcfa.agent.compiler import CompilationRequest
from dcfa.agent.runtime import AgentResponse, CausalAgentRuntime
from dcfa.artifact_validation import verify_run_directory
from dcfa.canonical import content_id, file_sha256, sha256_digest, to_primitive
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import DCFAError, ErrorCode
from dcfa.output import require_fresh_output_directory
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.schemas import AnalysisSpecification, DatasetManifest, QueryResult
from dcfa.tabcf_iv.development_dgp import generate_development_iv
from dcfa.tabcf_iv.pipeline import AnalysisRun, TabCFAnalysisEngine

PROTOCOL_VERSION = "track_a_gemini_live_smoke_v1"
GEMINI_MODEL = "gemini-3.6-flash"
GOOGLE_GENAI_VERSION = "2.18.1"
FROZEN_MANIFEST_HASH = "sha256:387c20ba2552a007b147e90daf944c30705d9f7ea22b64119d8878c5574878bb"
TRACE_FILENAME = "gemini_live_trace.json"


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


DEFAULT_MANIFEST_PATH = _repository_root() / "evaluation/configs/gemini_live_smoke_v1.json"


@dataclass(frozen=True)
class GeminiUsage:
    input_tokens: int
    output_tokens: int
    thought_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class GeminiLiveSmokeResult:
    response: AgentResponse
    run: AnalysisRun
    trace_id: str
    trace_path: Path
    interaction_id: str
    usage: GeminiUsage
    list_price_estimate_usd: str
    latency_ms: float


class _OutputBoundAnalysisTool:
    def __init__(self, output_dir: Path) -> None:
        self.engine = TabCFAnalysisEngine()
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
            raise ValueError("The Gemini smoke output directory is fixed by the caller.")
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


def _blocked(message: str, *, stage: str, context: dict[str, Any] | None = None) -> DCFAError:
    return DCFAError(
        ErrorCode.LLM_OUTPUT_INVALID,
        message,
        stage=stage,
        context=context,
    )


def read_gemini_api_key(api_key_file: Path) -> str:
    """Read one repository-external, owner-only Gemini API key file."""
    try:
        path = api_key_file.expanduser().resolve(strict=True)
    except OSError as exc:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The Gemini API key file is unavailable.",
            stage="gemini.credentials",
            context={"exception_type": type(exc).__name__},
        ) from exc
    repository = _repository_root()
    if path == repository or repository in path.parents:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The Gemini API key file must remain outside the repository.",
            stage="gemini.credentials",
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The Gemini API key file must not be accessible by group or others.",
            stage="gemini.credentials",
            context={"mode": oct(mode)},
        )
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    api_key = raw.strip()
    if len(lines) != 1 or len(api_key) < 20 or any(character.isspace() for character in api_key):
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The Gemini API key file must contain exactly one non-whitespace key.",
            stage="gemini.credentials",
        )
    return api_key


def _load_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    try:
        resolved = path.expanduser().resolve(strict=True)
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _blocked(
            "The frozen Gemini smoke manifest is unavailable or invalid JSON.",
            stage="gemini.manifest",
            context={"exception_type": type(exc).__name__},
        ) from exc
    observed_hash = file_sha256(resolved)
    if observed_hash != FROZEN_MANIFEST_HASH:
        raise _blocked(
            "The Gemini smoke manifest bytes do not match the frozen profile.",
            stage="gemini.manifest",
            context={"expected": FROZEN_MANIFEST_HASH, "observed": observed_hash},
        )
    required = {
        "version": PROTOCOL_VERSION,
        "provider": "google_gemini_developer_api",
        "sdk_package": "google-genai",
        "sdk_version": GOOGLE_GENAI_VERSION,
        "api_version": "v1beta",
        "model": GEMINI_MODEL,
        "store": False,
        "request_limit": 1,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise _blocked(
                "The Gemini smoke manifest does not match the frozen profile.",
                stage="gemini.manifest",
                context={"field": key, "expected": expected, "observed": payload.get(key)},
            )
    for key in (
        "fixture",
        "generation_config",
        "pricing",
        "response_schema",
        "expected_proposal",
    ):
        if not isinstance(payload.get(key), dict):
            raise _blocked(
                "The Gemini smoke manifest is missing a required object.",
                stage="gemini.manifest",
                context={"field": key},
            )
    if not isinstance(payload.get("system_instruction"), str) or not isinstance(
        payload.get("user_request"), str
    ):
        raise _blocked(
            "The Gemini smoke manifest is missing frozen prompt text.",
            stage="gemini.manifest",
        )
    return payload, resolved


def _model_input(manifest: dict[str, Any]) -> str:
    return json.dumps(
        {
            "available_columns": {
                "Y": "continuous outcome",
                "X": "continuous treatment",
                "Z": "scalar instrument",
            },
            "baseline_covariates": [],
            "intervention_labels": ["low", "center", "high"],
            "level_labels": {"median": 0.5},
            "user_request": manifest["user_request"],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def load_gemini_client(api_key: str) -> tuple[Any, str]:
    """Load the pinned Gemini SDK lazily and construct an authenticated client."""
    try:
        version = importlib.metadata.version("google-genai")
        module = importlib.import_module("google.genai")
    except Exception as exc:
        raise DCFAError(
            ErrorCode.LLM_IMPORT_FAILED,
            "The frozen google-genai dependency is unavailable.",
            stage="gemini.import",
            context={"exception_type": type(exc).__name__},
        ) from exc
    if version != GOOGLE_GENAI_VERSION:
        raise DCFAError(
            ErrorCode.LLM_IMPORT_FAILED,
            "The installed google-genai version does not match the frozen profile.",
            stage="gemini.import",
            context={"expected": GOOGLE_GENAI_VERSION, "observed": version},
        )
    return module.Client(api_key=api_key), version


def _parse_proposal(output_text: Any, expected: dict[str, Any]) -> dict[str, str]:
    if not isinstance(output_text, str):
        raise _blocked(
            "Gemini did not return a text proposal.",
            stage="gemini.output_validation",
        )
    try:
        proposal = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise _blocked(
            "Gemini returned invalid JSON; the response was discarded.",
            stage="gemini.output_validation",
        ) from exc
    if not isinstance(proposal, dict) or set(proposal) != set(expected):
        raise _blocked(
            "Gemini returned a proposal with an unexpected shape.",
            stage="gemini.output_validation",
        )
    if any(not isinstance(value, str) for value in proposal.values()):
        raise _blocked(
            "Gemini returned a proposal with invalid field types.",
            stage="gemini.output_validation",
        )
    if proposal != expected:
        raise _blocked(
            "Gemini did not reproduce the frozen clean-case specification.",
            stage="gemini.output_validation",
            context={
                "mismatched_fields": sorted(
                    key for key in expected if proposal[key] != expected[key]
                )
            },
        )
    return dict(proposal)


def _usage_from_interaction(interaction: Any) -> GeminiUsage:
    usage = getattr(interaction, "usage", None)
    fields = {
        "input_tokens": getattr(usage, "total_input_tokens", None),
        "output_tokens": getattr(usage, "total_output_tokens", None),
        "thought_tokens": getattr(usage, "total_thought_tokens", 0),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
    if fields["thought_tokens"] is None:
        fields["thought_tokens"] = 0
    if any(not isinstance(value, int) or value < 0 for value in fields.values()):
        raise _blocked(
            "Gemini did not return complete nonnegative token usage.",
            stage="gemini.usage_validation",
        )
    return GeminiUsage(**fields)


def _list_price_estimate(usage: GeminiUsage, pricing: dict[str, Any]) -> str:
    input_rate = Decimal(str(pricing["input_usd_per_million_tokens"]))
    output_rate = Decimal(str(pricing["output_and_thought_usd_per_million_tokens"]))
    estimate = (
        Decimal(usage.input_tokens) * input_rate
        + Decimal(usage.output_tokens + usage.thought_tokens) * output_rate
    ) / Decimal(1_000_000)
    return format(estimate.quantize(Decimal("0.00000001")), "f")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(to_primitive(payload), stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run_gemini_live_smoke(
    *,
    api_key_file: Path,
    output_dir: Path,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    client: Any | None = None,
    sdk_version: str | None = None,
) -> GeminiLiveSmokeResult:
    """Run one bounded Gemini compile call, then one deterministic synthetic analysis."""
    require_fresh_output_directory(output_dir)
    manifest, resolved_manifest = _load_manifest(manifest_path)
    api_key = read_gemini_api_key(api_key_file)
    if client is None:
        client, observed_sdk_version = load_gemini_client(api_key)
    else:
        observed_sdk_version = sdk_version or GOOGLE_GENAI_VERSION
    del api_key
    if observed_sdk_version != GOOGLE_GENAI_VERSION:
        raise DCFAError(
            ErrorCode.LLM_IMPORT_FAILED,
            "The observed google-genai version does not match the frozen profile.",
            stage="gemini.import",
            context={"expected": GOOGLE_GENAI_VERSION, "observed": observed_sdk_version},
        )

    model_input = _model_input(manifest)
    started = time.perf_counter()
    try:
        interaction = client.interactions.create(
            api_version=manifest["api_version"],
            model=manifest["model"],
            store=manifest["store"],
            system_instruction=manifest["system_instruction"],
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": manifest["response_schema"],
            },
            generation_config=manifest["generation_config"],
            labels={"project": "dcfa", "protocol": PROTOCOL_VERSION},
            input=model_input,
            timeout=float(manifest["timeout_seconds"]),
        )
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        raise DCFAError(
            ErrorCode.LLM_API_FAILED,
            "The single authorized Gemini request failed; no retry or fallback was attempted.",
            stage="gemini.api",
            context={
                "exception_type": type(exc).__name__,
                "status_code": status_code,
                "request_count": 1,
            },
        ) from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    latency_ms = (time.perf_counter() - started) * 1000.0

    if getattr(interaction, "status", None) != "completed":
        raise _blocked(
            "Gemini did not complete the frozen interaction.",
            stage="gemini.output_validation",
            context={"status": str(getattr(interaction, "status", None))},
        )
    interaction_id = str(getattr(interaction, "id", ""))
    if not interaction_id:
        raise _blocked(
            "Gemini did not return an interaction ID.",
            stage="gemini.output_validation",
        )
    proposal = _parse_proposal(
        getattr(interaction, "output_text", None),
        manifest["expected_proposal"],
    )
    usage = _usage_from_interaction(interaction)
    list_price_estimate_usd = _list_price_estimate(usage, manifest["pricing"])

    fixture = manifest["fixture"]
    dataset = generate_development_iv(
        n=int(fixture["row_count"]),
        seed=int(fixture["seed"]),
        instrument_strength=float(fixture["instrument_strength"]),
    )
    x_grid = tuple(
        float(value) for value in np.quantile(dataset.columns["X"], [0.1, 0.3, 0.5, 0.7, 0.9])
    )
    label_values = {"low": x_grid[1], "center": x_grid[2], "high": x_grid[3]}
    request = CompilationRequest(
        dataset_hash=dataset.manifest.dataset_hash,
        outcome=proposal["outcome"],
        treatment=proposal["treatment"],
        instrument=proposal["instrument"],
        treatment_type=proposal["treatment_type"],
        objective=proposal["objective"],
        intervention_grid=x_grid,
        x=label_values[proposal["x_label"]],
        comparison_x=label_values[proposal["comparison_x_label"]],
        level=0.5 if proposal["level_label"] == "median" else None,
        units="Y_units",
        confirmed_by_user=True,
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
        seed=int(fixture["seed"]),
    )
    analysis_dir = output_dir / "analysis"
    analysis_tool = _OutputBoundAnalysisTool(analysis_dir)
    response = CausalAgentRuntime(analysis_tool=analysis_tool).execute(
        request,
        dataset.columns,
        dataset.manifest,
    )
    if response.status != "completed" or analysis_tool.last_run is None:
        error_code = None if response.error is None else response.error.get("code")
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "The Gemini proposal did not produce a completed evidence-validated analysis.",
            stage="gemini.deterministic_execution",
            context={"agent_status": response.status, "agent_error_code": error_code},
        )
    run = analysis_tool.last_run

    manifest_id = content_id("llm_manifest", manifest)
    prompt_payload = {
        "system_instruction": manifest["system_instruction"],
        "model_input": model_input,
        "response_schema": manifest["response_schema"],
    }
    trace_body = {
        "protocol_version": PROTOCOL_VERSION,
        "track": Track.AGENT_BENCHMARK.value,
        "evidence_status": EvidenceStatus.TEST_ONLY.value,
        "data_label": "fixed_synthetic_gemini_live_smoke",
        "llm_manifest_id": manifest_id,
        "llm_manifest_hash": file_sha256(resolved_manifest),
        "prompt_hash": sha256_digest(prompt_payload),
        "request_hash": sha256_digest(model_input),
        "dcfa_source_tree_hash": dcfa_source_tree_hash(),
        "provider": manifest["provider"],
        "model": manifest["model"],
        "observed_model": str(getattr(interaction, "model", manifest["model"])),
        "sdk_package": manifest["sdk_package"],
        "sdk_version": observed_sdk_version,
        "api_version": manifest["api_version"],
        "store": False,
        "model_request_count": 1,
        "interaction_id": interaction_id,
        "interaction_status": str(interaction.status),
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "latency_ms": latency_ms,
        "usage": to_primitive(usage),
        "pricing": manifest["pricing"],
        "list_price_estimate_usd": list_price_estimate_usd,
        "list_price_is_not_billed_cost": True,
        "data_sent_to_gemini": [
            "frozen_user_request",
            "Y_X_Z_schema_contract",
            "symbolic_intervention_labels",
        ],
        "data_rows_sent_to_gemini": 0,
        "proposal": proposal,
        "deterministic_analysis": {
            "directory": "analysis",
            "run_id": run.bundle.run_id,
            "result_bundle_id": run.bundle.result_bundle_id,
            "specification_id": run.bundle.specification_id,
            "dataset_hash": run.bundle.dataset_hash,
            "execution_profile": run.bundle.execution_profile.value,
            "estimator_backend": run.bundle.estimator_backend.value,
            "evidence_status": run.bundle.evidence_status.value,
            "tool_calls": response.tool_calls,
            "retry_count": response.retry_count,
            "queries": [to_primitive(query) for query in response.queries],
            "warnings": [to_primitive(warning) for warning in response.warnings],
        },
        "limitations": [
            "One clean synthetic smoke is not a fixed-workflow versus full-agent benchmark.",
            "The sklearn fallback is development-only and is not TabCF evidence.",
            "The list-price estimate is not proof of the account's billed charge.",
        ],
    }
    trace_id = content_id("gemini_trace", trace_body)
    trace = {"trace_id": trace_id, **trace_body}
    trace_path = output_dir / TRACE_FILENAME
    _atomic_write_json(trace_path, trace)
    return GeminiLiveSmokeResult(
        response=response,
        run=run,
        trace_id=trace_id,
        trace_path=trace_path,
        interaction_id=interaction_id,
        usage=usage,
        list_price_estimate_usd=list_price_estimate_usd,
        latency_ms=latency_ms,
    )


def verify_gemini_live_smoke(
    output_dir: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Verify the live trace and its deterministic evidence without another API call."""
    manifest, resolved_manifest = _load_manifest(manifest_path)
    trace_path = output_dir / TRACE_FILENAME
    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The Gemini live trace is unavailable or invalid JSON.",
            stage="gemini.verification",
            context={"exception_type": type(exc).__name__},
        ) from exc
    trace_body = {key: value for key, value in trace.items() if key != "trace_id"}
    expected_trace_id = content_id("gemini_trace", trace_body)
    if trace.get("trace_id") != expected_trace_id:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The Gemini live trace content ID does not match its contents.",
            stage="gemini.verification",
        )
    exact_fields = {
        "protocol_version": PROTOCOL_VERSION,
        "track": Track.AGENT_BENCHMARK.value,
        "evidence_status": EvidenceStatus.TEST_ONLY.value,
        "llm_manifest_id": content_id("llm_manifest", manifest),
        "llm_manifest_hash": file_sha256(resolved_manifest),
        "dcfa_source_tree_hash": dcfa_source_tree_hash(),
        "provider": manifest["provider"],
        "model": manifest["model"],
        "sdk_package": manifest["sdk_package"],
        "sdk_version": manifest["sdk_version"],
        "api_version": manifest["api_version"],
        "store": False,
        "model_request_count": 1,
        "interaction_status": "completed",
        "data_rows_sent_to_gemini": 0,
        "data_sent_to_gemini": [
            "frozen_user_request",
            "Y_X_Z_schema_contract",
            "symbolic_intervention_labels",
        ],
        "pricing": manifest["pricing"],
        "proposal": manifest["expected_proposal"],
    }
    for key, expected in exact_fields.items():
        if trace.get(key) != expected:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "The Gemini live trace does not match the frozen manifest or current source.",
                stage="gemini.verification",
                context={"field": key},
            )
    prompt_payload = {
        "system_instruction": manifest["system_instruction"],
        "model_input": _model_input(manifest),
        "response_schema": manifest["response_schema"],
    }
    if trace.get("prompt_hash") != sha256_digest(prompt_payload) or trace.get(
        "request_hash"
    ) != sha256_digest(_model_input(manifest)):
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "The Gemini prompt or request hash does not match the frozen manifest.",
            stage="gemini.verification",
        )
    try:
        usage = GeminiUsage(**trace["usage"])
    except (KeyError, TypeError) as exc:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The Gemini usage record is incomplete.",
            stage="gemini.verification",
        ) from exc
    usage_values = to_primitive(usage).values()
    if any(not isinstance(value, int) or value < 0 for value in usage_values):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The Gemini usage record contains a negative token count.",
            stage="gemini.verification",
        )
    if trace.get("observed_model") not in {manifest["model"], f"models/{manifest['model']}"}:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The observed Gemini model does not match the frozen model.",
            stage="gemini.verification",
        )
    if not isinstance(trace.get("interaction_id"), str) or not trace["interaction_id"]:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The Gemini interaction ID is missing.",
            stage="gemini.verification",
        )
    if not isinstance(trace.get("latency_ms"), (int, float)) or trace["latency_ms"] < 0:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The Gemini latency record is invalid.",
            stage="gemini.verification",
        )
    if trace.get("list_price_estimate_usd") != _list_price_estimate(usage, manifest["pricing"]):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The Gemini list-price estimate does not match recorded usage.",
            stage="gemini.verification",
        )
    analysis_dir = output_dir / "analysis"
    analysis_verification = verify_run_directory(analysis_dir)
    bundle = json.loads((analysis_dir / "result_bundle.json").read_text(encoding="utf-8"))
    analysis = trace.get("deterministic_analysis", {})
    comparisons = {
        "run_id": bundle["run_id"],
        "result_bundle_id": bundle["result_bundle_id"],
        "specification_id": bundle["specification_id"],
        "dataset_hash": bundle["dataset_hash"],
        "execution_profile": bundle["execution_profile"],
        "estimator_backend": bundle["estimator_backend"],
        "evidence_status": bundle["evidence_status"],
        "queries": bundle["queries"],
        "warnings": bundle["warnings"],
    }
    for key, expected in comparisons.items():
        if analysis.get(key) != expected:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "The Gemini trace disagrees with the validated deterministic bundle.",
                stage="gemini.verification",
                context={"field": key},
            )
    return {
        "status": "valid",
        "trace_id": trace["trace_id"],
        "interaction_id": trace["interaction_id"],
        "model_request_count": 1,
        "analysis_status": analysis_verification["status"],
        "result_bundle_id": bundle["result_bundle_id"],
        "evidence_ids": [query["evidence_id"] for query in bundle["queries"]],
    }
