"""Authenticated whole-analysis transport for the existing ZeroGPU v2 executor."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from dcfa.agent.compiler import SpecificationCompiler
from dcfa.agent.runtime import AgentResponse
from dcfa.artifact_validation import verify_run_directory
from dcfa.canonical import to_primitive
from dcfa.constants import EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import DCFAError, ErrorCode
from dcfa.schemas import DatasetManifest, EvidenceRecord, ResultBundle
from dcfa.tabcf_iv.local_tabpfn import (
    LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
    make_local_tabpfn_v2_backend,
)
from dcfa_website_demo.gemini import GeminiWebsiteCompilation

MAX_WIRE_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 50_000_000


def unavailable(stage: str) -> DCFAError:
    return DCFAError(
        ErrorCode.V2_UNAVAILABLE,
        "The authenticated v2 analysis endpoint is unavailable.",
        stage=stage,
    )


def remote_token() -> str:
    from huggingface_hub import get_token

    configured = os.environ.get("DCFA_HF_TOKEN_FILE")
    if configured:
        path = Path(configured).expanduser().resolve()
        repository = Path(__file__).resolve().parents[2]
        if path.is_relative_to(repository) or path.stat().st_mode & 0o077:
            raise unavailable("v2.credentials")
        token = path.read_text().strip()
    else:
        token = get_token()
    if not token:
        raise unavailable("v2.credentials")
    return token


def make_payload(kwargs: dict) -> dict:
    # Never send Gemini trace, question, credentials, or local filesystem paths.
    keys = ("outcome", "treatment", "instrument", "interventions", "seed", "manifest")
    payload = {key: to_primitive(kwargs[key]) for key in keys}
    payload["columns"] = {key: value.tolist() for key, value in kwargs["columns"].items()}
    payload["compilation"] = to_primitive(replace(kwargs["compilation"], trace={}))
    return payload


def decode_payload(payload: Any) -> dict:
    from pydantic import TypeAdapter

    required = {
        "outcome",
        "treatment",
        "instrument",
        "interventions",
        "seed",
        "manifest",
        "columns",
        "compilation",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("Invalid v2 request fields.")
    if len(json.dumps(payload, allow_nan=False).encode()) > MAX_WIRE_BYTES:
        raise ValueError("The v2 request is too large.")
    compilation = TypeAdapter(GeminiWebsiteCompilation).validate_python(payload["compilation"])
    manifest = TypeAdapter(DatasetManifest).validate_python(payload["manifest"])
    if (
        compilation.trace
        or manifest.track is not Track.TABCF_IV
        or (
            manifest.execution_profile is not ExecutionProfile.LOCAL_DEVELOPMENT
            or manifest.evidence_status is not EvidenceStatus.DEVELOPMENT_ONLY
        )
    ):
        raise ValueError("The remote endpoint accepts development-only confirmed plans.")
    seed = payload["seed"]
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Invalid analysis seed.")
    from dcfa_website_demo.csv_upload import (
        CSVDataBoundary,
        ValidatedCSVColumns,
        _validate_column_names,
        assign_csv_roles,
    )

    columns = {key: np.asarray(value, dtype=float) for key, value in payload["columns"].items()}
    _validate_column_names(list(columns))
    if (
        len(columns) != 3
        or any(
            not key
            or key != key.strip()
            or value.ndim != 1
            or not 120 <= len(value) <= 256
            or not np.all(np.isfinite(value))
            or np.ptp(value) == 0
            for key, value in columns.items()
        )
        or len({len(value) for value in columns.values()}) != 1
    ):
        raise ValueError("Invalid three-column v2 data.")
    assigned = assign_csv_roles(
        ValidatedCSVColumns(columns, CSVDataBoundary.HF_ZEROGPU_LOCAL),
        outcome=payload["outcome"],
        treatment=payload["treatment"],
        instrument=payload["instrument"],
    )
    if (
        manifest.dataset_hash != assigned.manifest.dataset_hash
        or manifest.row_count != assigned.manifest.row_count
        or set(manifest.columns) != set(columns)
    ):
        raise ValueError("The v2 dataset does not match its manifest.")
    return dict(
        outcome=payload["outcome"],
        treatment=payload["treatment"],
        instrument=payload["instrument"],
        interventions=tuple(payload["interventions"]),
        seed=seed,
        manifest=manifest,
        columns=columns,
        compilation=compilation,
    )


def expected_specification(kwargs: dict):
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
        backend_parameters=LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
    )
    compiled = SpecificationCompiler().compile(request)
    if compiled.specification is None:
        raise ValueError("The remote analysis requires a complete confirmed specification.")
    return compiled.specification


def safe_extract(archive: Path, directory: Path) -> None:
    with zipfile.ZipFile(archive) as stream:
        entries = stream.infolist()
        if (
            not entries
            or len(entries) > 100
            or sum(e.file_size for e in entries) > MAX_ARCHIVE_BYTES
        ):
            raise ValueError("Invalid v2 archive size.")
        seen = set()
        for entry in entries:
            path = Path(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or len(path.parts) != 1
                or stat.S_ISLNK(entry.external_attr >> 16)
                or entry.filename in seen
            ):
                raise ValueError("Unsafe v2 archive member.")
            seen.add(entry.filename)
            target = directory / entry.filename
            if target.exists():
                raise ValueError("The v2 artifact would overwrite an existing file.")
        for entry in entries:
            with stream.open(entry) as source, (directory / entry.filename).open("xb") as target:
                shutil.copyfileobj(source, target)


def accept_result(directory: Path, kwargs: dict):
    from pydantic import TypeAdapter

    from dcfa_website_demo.app import PortfolioDemoResult

    verify_run_directory(directory)
    expected = expected_specification(kwargs)
    spec = json.loads((directory / "specification.json").read_text())
    if spec != to_primitive(expected):
        raise ValueError("Remote result changed the confirmed specification.")
    backend = json.loads((directory / "backend_manifest.json").read_text())
    params = dict(backend["parameters"])
    if params.get("model_version") != "v2" or params.get("device") != "cuda":
        raise ValueError("Remote result is not the CUDA v2 backend.")
    response = TypeAdapter(AgentResponse).validate_json(
        (directory / "remote_response.json").read_text()
    )
    bundle = json.loads((directory / "result_bundle.json").read_text())
    if (
        response.status != "completed"
        or response.specification_id != expected.specification_id
        or to_primitive(response.queries) != bundle["queries"]
        or to_primitive(response.warnings) != bundle["warnings"]
    ):
        raise ValueError("Remote response disagrees with the validated bundle.")
    from dcfa.evidence import EvidenceLedger
    from dcfa_website_demo.presentation import render_visitor_plot

    typed_bundle = TypeAdapter(ResultBundle).validate_python(bundle)
    ledger = EvidenceLedger(
        TypeAdapter(EvidenceRecord).validate_json(line)
        for line in (directory / "evidence_records.jsonl").read_text().splitlines()
    )
    trace = dict(kwargs["compilation"].trace, backend_access_mode="local_model")
    plot = directory / "website_interventional_summary.png"
    if typed_bundle.distribution is not None:
        from dcfa.distribution_reporting import (
            distribution_markdown,
            distribution_warning_html,
            render_distribution_plot,
        )

        trace["distribution_report"] = distribution_markdown(
            typed_bundle.distribution, typed_bundle.queries
        )
        trace["distribution_warnings"] = distribution_warning_html(typed_bundle)
        render_distribution_plot(typed_bundle, ledger, plot)
    else:
        render_visitor_plot(typed_bundle, ledger, plot)
    return PortfolioDemoResult(
        kwargs.get("result_scenario", "remote_v2"), response, plot, directory, trace
    )


def wait_for_job(job, directory: Path, space: str, *, timeout: float = 600):
    """Poll the same queued job; never submit again after an ambiguous failure."""
    import time

    from dcfa_website_demo.daily import write_record

    deadline = time.monotonic() + timeout
    while True:
        communicator = getattr(job, "communicator", None)
        event_id = getattr(communicator, "event_id", None)
        if not isinstance(event_id, str):
            event_id = None
        write_record(
            directory / "remote_job.json",
            {
                "space": space,
                "status": "submitted" if event_id is None else "pending",
                "job_id": event_id,
            },
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The remote job wait expired.")
        try:
            result = job.result(timeout=min(2, remaining))
            write_record(
                directory / "remote_job.json",
                {
                    "space": space,
                    "status": "returned",
                    "job_id": getattr(communicator, "event_id", None),
                },
            )
            return result
        except TimeoutError:
            if job.done():
                raise


def execute_remote(kwargs: dict, directory: Path):
    from gradio_client import Client

    from dcfa_website_demo.daily import write_record

    space = os.environ.get("DCFA_V2_SPACE", "GPChen01/dcfa-zerogpu")
    if len(space.split("/")) != 2 or any(c in space for c in ":?#\\"):
        raise unavailable("v2.destination")
    try:
        token = remote_token()
        client = Client(
            space,
            token=token,
            oauth_token=token,
            verbose=False,
            analytics_enabled=False,
            download_files=False,
            httpx_kwargs={"timeout": 30},
        )
        info = client.view_api(return_format="dict", print_info=False)
        if "/analyze_v2" not in info.get("named_endpoints", {}):
            raise unavailable("v2.endpoint")
    except DCFAError:
        if "client" in locals():
            client.close()
        raise
    except Exception as exc:
        if "client" in locals():
            client.close()
        raise unavailable("v2.connection") from exc
    try:
        job = client.submit(make_payload(kwargs), api_name="/analyze_v2")
        # submit is called exactly once; timeouts never enqueue another analysis.
        metadata, archive = wait_for_job(job, directory, space)
        if not isinstance(metadata, dict) or metadata.get("status") != "completed":
            remote_code = metadata.get("code") if isinstance(metadata, dict) else None
            code = (
                ErrorCode(remote_code)
                if remote_code in set(ErrorCode)
                else ErrorCode.V2_EXECUTION_FAILED
            )
            raise DCFAError(
                code,
                "Remote v2 analysis did not complete.",
                stage="v2.execution",
                context={
                    "remote_code": (
                        metadata.get("code")
                        if isinstance(metadata, dict) and metadata.get("code") in set(ErrorCode)
                        else "unknown"
                    )
                },
            )
        # Do not forward the HF token to an untrusted artifact host.
        import httpx

        url = archive.get("url") if isinstance(archive, dict) else None
        from urllib.parse import urlsplit

        if (
            not url
            or urlsplit(url).scheme != "https"
            or urlsplit(url).netloc != urlsplit(client.src).netloc
        ):
            raise ValueError("Unexpected v2 artifact origin.")
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "result.zip"
            with httpx.stream(
                "GET",
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                size = 0
                with archive_path.open("wb") as target:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_ARCHIVE_BYTES:
                            raise ValueError("The remote artifact is too large.")
                        target.write(chunk)
            safe_extract(archive_path, directory)
        result = accept_result(directory, kwargs)
        write_record(
            directory / "remote_job.json",
            {
                "space": space,
                "status": "completed",
                "job_id": getattr(getattr(job, "communicator", None), "event_id", None),
            },
        )
        return result
    except DCFAError:
        raise
    except Exception as exc:
        raise DCFAError(
            ErrorCode.V2_EXECUTION_FAILED,
            "Remote v2 execution or artifact retrieval failed; no resubmission occurred.",
            stage="v2.remote",
            context={"exception_type": type(exc).__name__},
        ) from exc
    finally:
        client.close()


def serve_v2(
    payload: dict,
    token: str,
    *,
    model_path: Path,
    output_root: Path,
    prediction_runner,
    authenticate=None,
):
    """Server boundary: authenticate first, then validate and run the complete analysis."""
    from huggingface_hub import HfApi

    from dcfa_website_demo.app import _execute_compiled_dataset
    from dcfa_website_demo.daily import write_record

    authenticate = authenticate or HfApi().whoami
    try:
        if not token or not authenticate(token=token).get("name"):
            raise ValueError("Missing authenticated identity.")
    except Exception as exc:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "Hugging Face authentication is required.",
            stage="v2.authentication",
        ) from exc
    kwargs = decode_payload(payload)
    expected_specification(kwargs)
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="remote-", dir=output_root) as temporary:
        result = _execute_compiled_dataset(
            **kwargs,
            result_scenario="remote_v2",
            output_scenario="remote-v2",
            output_root=Path(temporary),
            preserve_failure=True,
            backend_parameters=LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
            backend_factory=lambda spec: make_local_tabpfn_v2_backend(spec, model_path=model_path),
            prediction_runner=prediction_runner,
        )
        try:
            if result.response.status != "completed":
                return {
                    "status": "blocked",
                    "code": (result.response.error or {}).get("code"),
                }, None
            verify_run_directory(result.output_dir)
            write_record(result.output_dir / "remote_response.json", result.response)
            archive_root = Path(os.environ.get("GRADIO_TEMP_DIR", "/tmp/gradio"))
            archive_root.mkdir(parents=True, exist_ok=True)
            import uuid

            archive = archive_root / f"v2-{uuid.uuid4().hex}.zip"
            with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as stream:
                for path in result.output_dir.iterdir():
                    if path.is_file():
                        if token.encode() in path.read_bytes():
                            archive.unlink(missing_ok=True)
                            raise ValueError("Credential reached artifact.")
                        stream.write(path, path.name)
            return {"status": "completed"}, str(archive)
        finally:
            if result.output_dir is not None:
                shutil.rmtree(result.output_dir)


def availability_notice() -> str:
    """Read-only capability check; it never promises a GPU allocation."""
    from dcfa_website_demo.daily import v2_destination

    if os.environ.get("DCFA_V2_EXECUTOR", "zerogpu") == "local_cuda":
        import importlib.util

        if importlib.util.find_spec("torch") is None:
            return "**v2 unavailable:** Torch/CUDA is not installed in this runtime."
        import torch

        configured = os.environ.get("DCFA_V2_MODEL_PATH", "")
        ready = torch.cuda.is_available() and Path(configured).is_file()
        return "**v2 configuration:** " + (
            "CUDA and checkpoint available."
            if ready
            else "CUDA or the configured checkpoint is unavailable."
        )
    try:
        from gradio_client import Client

        token = remote_token()
        client = Client(
            os.environ.get("DCFA_V2_SPACE", "GPChen01/dcfa-zerogpu"),
            token=token,
            verbose=False,
            analytics_enabled=False,
            httpx_kwargs={"timeout": 15},
        )
        try:
            info = client.view_api(return_format="dict", print_info=False)
            present = "/analyze_v2" in info.get("named_endpoints", {})
        finally:
            client.close()
        if present:
            return (
                "**v2 endpoint available:** "
                + v2_destination()
                + ". Authentication and GPU allocation are checked when the task runs."
            )
        return (
            "**v2 unavailable:** The configured Space needs an updated analysis service. "
            "Deployment is pending. 3.5 API can still run."
        )
    except Exception:
        return "**v2 availability unverified:** Check the configured HF credential and Space."
