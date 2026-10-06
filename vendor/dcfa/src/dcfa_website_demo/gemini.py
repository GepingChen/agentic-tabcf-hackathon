"""Bounded Gemini specification compiler for the local website demo."""

from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dcfa.agent.gemini_live import (
    GOOGLE_GENAI_VERSION,
    load_gemini_client,
    read_gemini_api_key,
)
from dcfa.canonical import content_id, file_sha256, sha256_digest, to_primitive
from dcfa.errors import DCFAError, ErrorCode
from dcfa.schemas import DistributionRequest

PROTOCOL_VERSION = "website_demo_gemini_v2"
GEMINI_MODEL = "gemini-3.6-flash"
TRACE_FILENAME = "gemini_compilation.json"
SUPPORTED_OBJECTIVES = frozenset({"mean", "quantile", "mean_contrast", "quantile_contrast"})
INTERVENTION_LABELS = frozenset({"low", "center", "high"})


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_CONFIG_PATH = _repository_root() / "evaluation/configs/website_demo_gemini_v2.json"


def website_gemini_config_file_from_environment() -> Path:
    """Resolve the versioned website prompt/model profile."""
    return Path(os.environ.get("DCFA_WEBSITE_GEMINI_CONFIG_FILE", str(DEFAULT_CONFIG_PATH)))


@dataclass(frozen=True)
class GeminiWebsiteCompilation:
    outcome: str
    treatment: str
    instrument: str
    objective: str
    x_label: str
    comparison_x_label: str | None
    level: float | None
    trace: dict[str, Any]
    distribution: DistributionRequest | None = None


def _load_config(
    path: Path,
    *,
    expected_version: str = PROTOCOL_VERSION,
) -> tuple[dict[str, Any], Path]:
    try:
        resolved = path.expanduser().resolve(strict=True)
        config = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "The website Gemini configuration is unavailable or invalid JSON.",
            stage="website_demo.gemini_config",
            context={"exception_type": type(exc).__name__},
        ) from exc
    required = {
        "version": expected_version,
        "provider": "google_gemini_developer_api",
        "sdk_package": "google-genai",
        "sdk_version": GOOGLE_GENAI_VERSION,
        "api_version": "v1beta",
        "model": GEMINI_MODEL,
        "store": False,
        "request_limit": 1,
    }
    for key, expected in required.items():
        if config.get(key) != expected:
            raise DCFAError(
                ErrorCode.LLM_OUTPUT_INVALID,
                "The website Gemini configuration does not match the supported profile.",
                stage="website_demo.gemini_config",
                context={"field": key, "expected": expected, "observed": config.get(key)},
            )
    for key in ("generation_config", "response_schema"):
        if not isinstance(config.get(key), dict):
            raise DCFAError(
                ErrorCode.LLM_OUTPUT_INVALID,
                "The website Gemini configuration is missing a required object.",
                stage="website_demo.gemini_config",
                context={"field": key},
            )
    if not isinstance(config.get("system_instruction"), str):
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "The website Gemini configuration is missing its system instruction.",
            stage="website_demo.gemini_config",
        )
    return config, resolved


def validate_website_gemini_config(
    path: Path | None = None,
    *,
    expected_version: str = PROTOCOL_VERSION,
) -> str:
    """Validate the configured profile without importing the SDK or making a request."""
    _, resolved = _load_config(
        path or website_gemini_config_file_from_environment(),
        expected_version=expected_version,
    )
    return file_sha256(resolved)


def _role_context(
    available_columns: tuple[str, str, str] | None,
    role_overrides: dict[str, str | None] | None,
) -> tuple[tuple[str, str, str], dict[str, str], bool]:
    if available_columns is None:
        if role_overrides and any(value for value in role_overrides.values()):
            raise ValueError("Column role overrides require an uploaded CSV header.")
        return ("Y", "X", "Z"), {}, False
    columns = tuple(str(value).strip() for value in available_columns)
    if len(columns) != 3 or any(not value for value in columns) or len(set(columns)) != 3:
        raise ValueError("The CSV must provide exactly three distinct column names.")
    allowed_roles = {"outcome", "treatment", "instrument"}
    supplied = role_overrides or {}
    if set(supplied) - allowed_roles:
        raise ValueError("Column role overrides contain an unsupported role.")
    normalized: dict[str, str] = {}
    for role, raw_value in supplied.items():
        if raw_value is None or not str(raw_value).strip():
            continue
        value = str(raw_value).strip()
        if value not in columns:
            raise ValueError(f"The optional {role} override does not match a CSV column.")
        normalized[role] = value
    if len(set(normalized.values())) != len(normalized):
        raise ValueError("Optional role overrides must refer to distinct CSV columns.")
    return columns, normalized, True


def _model_input(
    question: str,
    *,
    columns: tuple[str, str, str],
    role_overrides: dict[str, str],
    csv_mode: bool,
) -> str:
    normalized = question.strip()
    if not 8 <= len(normalized) <= 1000 or "\x00" in normalized:
        raise ValueError("The analysis question must contain 8–1000 plain-text characters.")
    payload: dict[str, Any] = {
        "available_roles": {
            "outcome": "continuous outcome",
            "treatment": "continuous treatment",
            "instrument": "scalar instrument",
        },
        "baseline_covariates": [],
        "intervention_labels": ["low", "center", "high"],
        "supported_summaries": ["mean", "median quantile"],
        "user_question": normalized,
    }
    if csv_mode:
        payload["available_columns"] = list(columns)
        payload["optional_role_overrides"] = role_overrides
    else:
        payload["fixed_role_mapping"] = {
            "outcome": "Y",
            "treatment": "X",
            "instrument": "Z",
        }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _response_schema(
    configured_schema: dict[str, Any],
    *,
    columns: tuple[str, str, str],
    role_overrides: dict[str, str],
    csv_mode: bool,
) -> dict[str, Any]:
    schema = deepcopy(configured_schema)
    if csv_mode:
        for role in ("outcome", "treatment", "instrument"):
            schema["properties"][role]["enum"] = (
                [role_overrides[role]] if role in role_overrides else list(columns)
            )
    return schema


def _parse_proposal(output_text: Any) -> dict[str, str]:
    if not isinstance(output_text, str):
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini did not return a text specification proposal.",
            stage="website_demo.gemini_output",
        )
    try:
        proposal = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini returned invalid JSON; the proposal was discarded.",
            stage="website_demo.gemini_output",
        ) from exc
    expected_fields = {
        "decision",
        "reason",
        "outcome",
        "treatment",
        "instrument",
        "treatment_type",
        "objective",
        "x_label",
        "comparison_x_label",
        "level_label",
    }
    if (
        not isinstance(proposal, dict)
        or set(proposal) != expected_fields
        or any(not isinstance(value, str) for value in proposal.values())
    ):
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini returned a proposal with an unexpected shape.",
            stage="website_demo.gemini_output",
        )
    return proposal


def _validate_proposal(
    proposal: dict[str, str],
    *,
    columns: tuple[str, str, str],
    role_overrides: dict[str, str],
    csv_mode: bool,
    allow_distribution: bool = False,
) -> tuple[str, str, str, str, str, str | None, float | None]:
    decision = proposal["decision"]
    reason = proposal["reason"].strip()
    if (
        decision not in {"analyze", "clarify", "block"}
        or not 1 <= len(reason) <= 240
        or any(character.isdigit() for character in reason)
    ):
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini returned an invalid decision or reason.",
            stage="website_demo.gemini_output",
        )
    if decision != "analyze":
        message = (
            "Gemini requested clarification. Ask for a mean or median summary or contrast "
            "using low, center, or high treatment."
            if decision == "clarify"
            else "Gemini blocked a request outside the continuous-treatment no-W demo scope."
        )
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            message,
            stage="website_demo.gemini_decision",
            context={"decision": decision},
        )
    role_mapping = tuple(proposal[role] for role in ("outcome", "treatment", "instrument"))
    if proposal["treatment_type"] != "continuous":
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini changed the continuous-treatment contract.",
            stage="website_demo.gemini_output",
        )
    if csv_mode:
        if (
            any(value not in columns for value in role_mapping)
            or len(set(role_mapping)) != 3
            or any(proposal[role] != value for role, value in role_overrides.items())
        ):
            raise DCFAError(
                ErrorCode.LLM_OUTPUT_INVALID,
                "Gemini returned an invalid or conflicting CSV role mapping.",
                stage="website_demo.gemini_output",
            )
    elif role_mapping != ("Y", "X", "Z"):
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini changed the fixed Y/X/Z role mapping.",
            stage="website_demo.gemini_output",
        )
    objective = proposal["objective"]
    x_label = proposal["x_label"]
    comparison_label = proposal["comparison_x_label"]
    level_label = proposal["level_label"]
    if allow_distribution and objective == "distribution":
        if (x_label, comparison_label, level_label) != ("exact", "exact", "quartiles"):
            raise DCFAError(
                ErrorCode.LLM_OUTPUT_INVALID,
                "Exact distribution requests cannot use symbolic interventions.",
                stage="website_demo.gemini_output",
            )
        return (*role_mapping, objective, x_label, comparison_label, None)
    if objective not in SUPPORTED_OBJECTIVES or x_label not in INTERVENTION_LABELS:
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini selected an unsupported objective or intervention label.",
            stage="website_demo.gemini_output",
        )
    is_contrast = objective.endswith("_contrast")
    if is_contrast:
        if comparison_label not in INTERVENTION_LABELS or comparison_label == x_label:
            raise DCFAError(
                ErrorCode.LLM_OUTPUT_INVALID,
                "A contrast requires two distinct symbolic intervention labels.",
                stage="website_demo.gemini_output",
            )
        comparison: str | None = comparison_label
    else:
        if comparison_label != "none":
            raise DCFAError(
                ErrorCode.LLM_OUTPUT_INVALID,
                "A non-contrast proposal must not include a comparison intervention.",
                stage="website_demo.gemini_output",
            )
        comparison = None
    is_quantile = objective.startswith("quantile")
    if (is_quantile and level_label != "median") or (not is_quantile and level_label != "none"):
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini returned an objective and summary level that do not agree.",
            stage="website_demo.gemini_output",
        )
    return (
        proposal["outcome"],
        proposal["treatment"],
        proposal["instrument"],
        objective,
        x_label,
        comparison,
        0.5 if is_quantile else None,
    )


def _usage_payload(interaction: Any) -> dict[str, int]:
    usage = getattr(interaction, "usage", None)
    payload: dict[str, Any] = {
        "input_tokens": getattr(usage, "total_input_tokens", None),
        "output_tokens": getattr(usage, "total_output_tokens", None),
        "thought_tokens": getattr(usage, "total_thought_tokens", 0),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
    if payload["thought_tokens"] is None:
        payload["thought_tokens"] = 0
    if any(not isinstance(value, int) or value < 0 for value in payload.values()):
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini did not return complete nonnegative token usage.",
            stage="website_demo.gemini_usage",
        )
    return {key: int(value) for key, value in payload.items()}


def compile_website_question(
    question: str,
    *,
    api_key_file: Path,
    client: Any | None = None,
    sdk_version: str | None = None,
    config_path: Path | None = None,
    available_columns: tuple[str, str, str] | None = None,
    role_overrides: dict[str, str | None] | None = None,
) -> GeminiWebsiteCompilation:
    """Compile one bounded question and optional CSV roles with no data rows."""
    config, resolved_config = _load_config(
        config_path or website_gemini_config_file_from_environment()
    )
    columns, normalized_overrides, csv_mode = _role_context(
        available_columns,
        role_overrides,
    )
    model_input = _model_input(
        question,
        columns=columns,
        role_overrides=normalized_overrides,
        csv_mode=csv_mode,
    )
    response_schema = _response_schema(
        config["response_schema"],
        columns=columns,
        role_overrides=normalized_overrides,
        csv_mode=csv_mode,
    )
    api_key = read_gemini_api_key(api_key_file)
    if client is None:
        client, observed_sdk_version = load_gemini_client(api_key)
    else:
        observed_sdk_version = sdk_version or GOOGLE_GENAI_VERSION
    del api_key
    if observed_sdk_version != GOOGLE_GENAI_VERSION:
        raise DCFAError(
            ErrorCode.LLM_IMPORT_FAILED,
            "The observed google-genai version does not match the website profile.",
            stage="website_demo.gemini_import",
            context={"expected": GOOGLE_GENAI_VERSION, "observed": observed_sdk_version},
        )
    started = time.perf_counter()
    try:
        interaction = client.interactions.create(
            api_version=config["api_version"],
            model=config["model"],
            store=config["store"],
            system_instruction=config["system_instruction"],
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": response_schema,
            },
            generation_config=config["generation_config"],
            input=model_input,
            timeout=float(config["timeout_seconds"]),
        )
    except Exception as exc:
        raise DCFAError(
            ErrorCode.LLM_API_FAILED,
            "The Gemini compilation request failed; no retry or fallback was attempted.",
            stage="website_demo.gemini_api",
            context={
                "exception_type": type(exc).__name__,
                "status_code": getattr(exc, "status_code", None),
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
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "Gemini did not complete the specification interaction.",
            stage="website_demo.gemini_output",
            context={"status": str(getattr(interaction, "status", None))},
        )
    raw_interaction_id = getattr(interaction, "id", None)
    interaction_id = (
        raw_interaction_id if isinstance(raw_interaction_id, str) and raw_interaction_id else None
    )
    proposal = _parse_proposal(getattr(interaction, "output_text", None))
    (
        outcome,
        treatment,
        instrument,
        objective,
        x_label,
        comparison_label,
        level,
    ) = _validate_proposal(
        proposal,
        columns=columns,
        role_overrides=normalized_overrides,
        csv_mode=csv_mode,
    )
    trace_body = {
        "protocol_version": PROTOCOL_VERSION,
        "provider": config["provider"],
        "model": config["model"],
        "observed_model": str(getattr(interaction, "model", config["model"])),
        "sdk_package": config["sdk_package"],
        "sdk_version": observed_sdk_version,
        "api_version": config["api_version"],
        "store": False,
        "model_request_count": 1,
        "interaction_id": interaction_id,
        "interaction_status": str(interaction.status),
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "latency_ms": latency_ms,
        "usage": _usage_payload(interaction),
        "config_hash": file_sha256(resolved_config),
        "prompt_hash": sha256_digest(
            {
                "system_instruction": config["system_instruction"],
                "model_input": model_input,
                "response_schema": response_schema,
            }
        ),
        "request_hash": sha256_digest(model_input),
        "data_sent_to_gemini": (
            [
                "user_question",
                "csv_column_names",
                "optional_role_overrides",
                "Y_X_Z_schema_contract",
                "symbolic_intervention_labels",
            ]
            if csv_mode
            else [
                "user_question",
                "Y_X_Z_schema_contract",
                "symbolic_intervention_labels",
            ]
        ),
        "data_rows_sent_to_gemini": 0,
        "actual_intervention_values_sent_to_gemini": 0,
        "proposal": proposal,
    }
    return GeminiWebsiteCompilation(
        outcome=outcome,
        treatment=treatment,
        instrument=instrument,
        objective=objective,
        x_label=x_label,
        comparison_x_label=comparison_label,
        level=level,
        trace={"trace_id": content_id("website_gemini_trace", trace_body), **trace_body},
    )


def write_compilation_trace(output_dir: Path, trace: dict[str, Any]) -> Path:
    """Persist the non-secret Gemini compile trace beside a successful analysis."""
    path = output_dir / TRACE_FILENAME
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(to_primitive(trace), stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    return path
