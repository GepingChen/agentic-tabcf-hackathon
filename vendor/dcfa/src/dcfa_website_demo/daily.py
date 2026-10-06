"""Explicit, development-only daily analysis selection outside the statistical core."""

from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from dcfa.agent.runtime import AgentResponse
from dcfa.agent.state import AgentState
from dcfa.canonical import to_primitive
from dcfa.errors import DCFAError, ErrorCode
from dcfa.tabcf_iv.local_tabpfn import (
    LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
    make_local_tabpfn_v2_backend,
)
from dcfa.tabcf_iv.managed_client import (
    MANAGED_BACKEND_PARAMETERS,
    MANAGED_CLIENT_VERSION,
    TabPFNClientBackend,
)
from dcfa.tabcf_iv.managed_session import managed_session, quota_error


class AnalysisMode(StrEnum):
    API_PREFERRED = "api_preferred"
    API_ONLY = "api_only"
    V2_ONLY = "v2_only"


MODE_CHOICES = [
    ("3.5 API first; use v2 only after confirmed quota exhaustion", "api_preferred"),
    ("3.5 API only; stop when quota is exhausted", "api_only"),
    ("TabPFN v2 only", "v2_only"),
]


def v2_destination() -> str:
    if os.environ.get("DCFA_V2_EXECUTOR", "zerogpu") == "local_cuda":
        return "local CUDA runtime"
    return "Hugging Face Space " + os.environ.get("DCFA_V2_SPACE", "GPChen01/dcfa-zerogpu")


def transfer_notice(mode: str, *, v2_location: str | None = None) -> str:
    selected = AnalysisMode(mode)
    destination = v2_location or v2_destination()
    destinations = {
        AnalysisMode.API_ONLY: "Selected Y/X/Z rows go to Prior Labs.",
        AnalysisMode.V2_ONLY: (f"Y/X/Z rows and the confirmed plan go to {destination}."),
        AnalysisMode.API_PREFERRED: (
            "Selected Y/X/Z rows go to Prior Labs. Only after confirmed API quota exhaustion, "
            f"the same rows and confirmed plan go to {destination} for a complete v2 rerun. "
            "Results may differ. No further confirmation is requested for that switch."
        ),
    }
    availability = (
        " If v2 is unavailable, the analysis stops when v2 is selected."
        if selected is AnalysisMode.V2_ONLY
        else " An unavailable fallback stops the analysis after confirmed API quota exhaustion."
        if selected is AnalysisMode.API_PREFERRED
        else ""
    )
    return (
        "**Data and model policy:** Question text and column names go to Google Gemini. "
        + destinations[selected]
        + " No automatic purchases, upgrades, CPU or sklearn substitution. "
        + availability
    )


def write_record(path: Path, value: Any) -> None:
    path.write_text(json.dumps(to_primitive(value), indent=2, allow_nan=False), encoding="utf-8")


def blocked_result(error: DCFAError, directory: Path, scenario: str, trace: dict):
    from dcfa_website_demo.app import PortfolioDemoResult

    return PortfolioDemoResult(
        scenario=scenario,
        output_dir=directory,
        plot_path=None,
        llm_trace=trace,
        response=AgentResponse(
            status="blocked",
            final_state=AgentState.BLOCKED,
            specification_id=None,
            result_bundle_id=None,
            queries=(),
            warnings=(),
            clarification_questions=(),
            error=error.to_dict(),
            tool_calls=0,
            retry_count=0,
            state_events=(),
        ),
    )


def execute_api_attempt(kwargs: dict, directory: Path, settings: dict):
    import importlib.metadata

    from dcfa.tabcf_iv.managed_smoke import load_managed_client_module, read_managed_token_file
    from dcfa_website_demo.app import _execute_compiled_dataset, managed_token_file_from_environment

    client = settings.get("client_module") or load_managed_client_module()
    version = settings.get("client_version") or importlib.metadata.version("tabpfn-client")
    if version != MANAGED_CLIENT_VERSION:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "The managed client version is unsupported.",
            stage="daily.api.version",
        )
    token = read_managed_token_file(
        settings.get("token_file") or managed_token_file_from_environment()
    )
    with managed_session(
        client, token, capture_errors=settings.get("client_module") is None
    ) as usage:
        observed = usage() if settings.get("client_module") is None else None
        if observed is not None and observed.exhausted:
            raise quota_error(observed, stage="daily.api.pre_execution")
        result = _execute_compiled_dataset(
            **kwargs,
            reserved_output_dir=directory,
            preserve_failure=True,
            backend_parameters=MANAGED_BACKEND_PARAMETERS,
            backend_factory=lambda spec: TabPFNClientBackend.from_specification(
                spec, regressor_class=client.TabPFNRegressor, client_version=version
            ),
        )
        after = usage() if settings.get("client_module") is None else None
        return replace(
            result,
            llm_trace=dict(
                result.llm_trace,
                api_usage={
                    "before": to_primitive(observed),
                    "after": to_primitive(after),
                },
            ),
        )


def execute_v2_attempt(kwargs: dict, directory: Path, settings: dict):
    from dcfa_website_demo.app import _execute_compiled_dataset

    executor = os.environ.get("DCFA_V2_EXECUTOR", "zerogpu")
    if executor == "zerogpu":
        from dcfa_website_demo.v2_remote import execute_remote

        return execute_remote(kwargs, directory)
    if executor != "local_cuda":
        raise DCFAError(
            ErrorCode.V2_UNAVAILABLE,
            "Unknown v2 execution location.",
            stage="daily.v2.configuration",
        )
    model = os.environ.get("DCFA_V2_MODEL_PATH")
    try:
        import torch

        available = torch.cuda.is_available()
    except ImportError:
        available = False
    if not available or not model or not Path(model).is_file():
        raise DCFAError(
            ErrorCode.V2_UNAVAILABLE,
            "TabPFN v2 requires CUDA and the configured v2 checkpoint.",
            stage="daily.v2.availability",
        )
    return _execute_compiled_dataset(
        **kwargs,
        reserved_output_dir=directory,
        preserve_failure=True,
        backend_parameters=LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
        backend_factory=lambda spec: make_local_tabpfn_v2_backend(spec, model_path=Path(model)),
    )


def execution_summary(record: dict) -> str:
    labels = dict((value, label) for label, value in MODE_CHOICES)
    lines = [f"Analysis policy: {labels[record['mode']]}. "]
    if record.get("actual_model"):
        lines.append(f"Actual model: **{record['actual_model']}** (development_only).")
    if record.get("fallback_completed"):
        lines.append("3.5 额度已用完，本次改用 TabPFN v2，结果可能不同。")
    elif record.get("fallback_attempted"):
        lines.append(
            "3.5 quota was exhausted; the v2 attempt did not complete. No result is claimed."
        )
    if record.get("error_code"):
        lines.append(f"Stopped: `{record['error_code']}`.")
    return "\n\n".join(lines)


def validate_daily_request(kwargs: dict, parameters: tuple):
    """Apply existing input/profile validation before sending rows to either service."""
    from dcfa.agent.compiler import SpecificationCompiler
    from dcfa.tabcf_iv.validation import (
        validate_tabcf_data,
        validate_tabcf_dataset_manifest,
        validate_tabcf_specification,
    )
    from dcfa_website_demo.app import compiled_request

    request = compiled_request(
        **{
            key: kwargs[key]
            for key in (
                "outcome",
                "treatment",
                "instrument",
                "compilation",
                "interventions",
                "manifest",
                "seed",
            )
        },
        backend_parameters=parameters,
    )
    specification = SpecificationCompiler().compile(request).specification
    if specification is None:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "The daily request requires a complete confirmed plan.",
            stage="daily.request",
        )
    validate_tabcf_specification(specification)
    arrays = validate_tabcf_data(kwargs["columns"], specification)
    validate_tabcf_dataset_manifest(kwargs["manifest"], specification, arrays)


def execute_daily_dataset(
    *,
    mode: str,
    compiled_kwargs: dict,
    managed_settings: dict,
    api_executor=None,
    v2_executor=None,
    v2_location: str | None = None,
):
    """At most two independent complete attempts; never resume across models."""
    from dcfa_website_demo.app import _reserve_output_directory

    selected = AnalysisMode(mode)
    api_executor = api_executor or execute_api_attempt
    v2_executor = v2_executor or execute_v2_attempt
    root = _reserve_output_directory(
        Path(compiled_kwargs["output_root"]),
        "daily-" + compiled_kwargs["output_scenario"],
        compiled_kwargs["seed"],
    )
    record = {
        "mode": selected.value,
        "v2_destination": v2_location or v2_destination(),
        "attempts": [],
        "fallback_attempted": False,
        "fallback_completed": False,
        "actual_model": None,
    }
    names = ["v2"] if selected is AnalysisMode.V2_ONLY else ["api"]
    for name in names:
        directory = root / f"attempt-{len(record['attempts']) + 1}-{name}"
        directory.mkdir()
        attempt = {"backend": name, "directory": directory.name, "status": "running"}
        record["attempts"].append(attempt)
        write_record(root / "daily_execution.json", record)
        attempt_started = time.perf_counter()
        kwargs = dict(compiled_kwargs, compilation=deepcopy(compiled_kwargs["compilation"]))
        try:
            validate_daily_request(
                kwargs,
                MANAGED_BACKEND_PARAMETERS if name == "api" else LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
            )
            executor = api_executor if name == "api" else v2_executor
            result = executor(kwargs, directory, managed_settings)
        except DCFAError as exc:
            result = blocked_result(
                exc, directory, kwargs["result_scenario"], kwargs["compilation"].trace
            )
        except Exception as exc:
            code = (
                ErrorCode.V2_EXECUTION_FAILED if name == "v2" else ErrorCode.MANAGED_SERVICE_FAILED
            )
            result = blocked_result(
                DCFAError(
                    code,
                    "Analysis execution failed.",
                    stage=f"daily.{name}",
                    context={"exception_type": type(exc).__name__},
                ),
                directory,
                kwargs["result_scenario"],
                kwargs["compilation"].trace,
            )
        attempt["client_wall_seconds"] = time.perf_counter() - attempt_started
        attempt["provider_server_seconds"] = None
        attempt.update(status=result.response.status, error=result.response.error)
        if "api_usage" in result.llm_trace:
            attempt["api_usage"] = result.llm_trace["api_usage"]
        write_record(directory / "attempt.json", attempt)
        if result.response.status == "completed":
            # The numerical bundle remains authoritative, including all warnings.
            from dcfa.artifact_validation import verify_run_directory

            try:
                verify_run_directory(directory)
                backend = json.loads((directory / "backend_manifest.json").read_text())
                params = dict(backend["parameters"])
                record["actual_model"] = (
                    params.get("model_path") if name == "api" else params.get("model_version")
                )
                if not record["actual_model"]:
                    raise ValueError("Missing model identity")
                record["actual_model"] = "TabPFN " + record["actual_model"]
                record["backend_manifest"] = backend
                record["fallback_completed"] = bool(record["fallback_attempted"])
            except Exception as exc:
                result = blocked_result(
                    DCFAError(
                        ErrorCode.EVIDENCE_MISMATCH,
                        "The daily result could not be verified.",
                        stage="daily.artifacts",
                        context={"exception_type": type(exc).__name__},
                    ),
                    directory,
                    kwargs["result_scenario"],
                    kwargs["compilation"].trace,
                )
                attempt.update(status="blocked", error=result.response.error)
                write_record(directory / "attempt.json", attempt)
        code = (result.response.error or {}).get("code")
        if (
            name == "api"
            and selected is AnalysisMode.API_PREFERRED
            and code == ErrorCode.MANAGED_QUOTA_EXHAUSTED
        ):
            record["fallback_attempted"] = True
            record["fallback_reason"] = result.response.error
            names.append("v2")
            continue
        record["error_code"] = code
        break
    write_record(root / "daily_execution.json", record)
    write_record(directory / "daily_execution.json", record)
    summary = execution_summary(record)
    report = directory / "report.md"
    (directory / "analysis_report.md").write_text(
        summary
        + "\n\n"
        + (
            report.read_text() if report.is_file() and result.response.status == "completed" else ""
        ),
        encoding="utf-8",
    )
    trace = dict(result.llm_trace, daily_execution=record, daily_summary=summary)
    return replace(result, llm_trace=trace)


def archive_daily_result(result) -> str | None:
    """Package the current attempts and report without overwriting earlier runs."""
    import zipfile

    if result.output_dir is None or "daily_execution" not in result.llm_trace:
        return None
    root = result.output_dir.parent
    archive = root / "analysis_artifacts.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as stream:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path != archive:
                stream.write(path, str(path.relative_to(root)))
    return str(archive)
