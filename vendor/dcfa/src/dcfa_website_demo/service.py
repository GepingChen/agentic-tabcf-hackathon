"""Deployment wrapper for the bounded DCFA development workflow demo."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

from dcfa import __version__
from dcfa.agent.gemini_live import read_gemini_api_key
from dcfa.errors import DCFAError
from dcfa.tabcf_iv.managed_client import MANAGED_MODEL_PATH
from dcfa.tabcf_iv.managed_smoke import read_managed_token_file
from dcfa_website_demo.app import (
    DEFAULT_OUTPUT_ROOT,
    DEMO_CSS,
    build_app,
    build_demo_theme,
    gemini_api_key_file_from_environment,
    managed_token_file_from_environment,
)
from dcfa_website_demo.gemini import GEMINI_MODEL, validate_website_gemini_config


def output_root_from_environment() -> Path:
    """Resolve the local artifact root without importing a statistical backend."""
    return Path(os.environ.get("DCFA_OUTPUT_ROOT", str(DEFAULT_OUTPUT_ROOT)))


def output_root_is_writable(output_root: Path) -> bool:
    """Check the nearest existing parent without creating or deleting material."""
    candidate = output_root.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate.is_dir() and os.access(candidate, os.W_OK)


def require_available_port(host: str, port: int) -> None:
    """Fail with an operator-readable message if an older service owns the port."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError as exc:
            raise RuntimeError(
                f"Cannot start the DCFA local demo: {host}:{port} is already in use. "
                "Stop the existing demo or choose a different PORT, then verify the page build ID."
            ) from exc


def build_service(
    *,
    fixed_analysis_mode: str | None = None,
    presentation_title: str = "Agentic TabCF",
    local_csv_dialogue: bool = False,
) -> Any:
    """Build a health-checkable ASGI service with the Gradio demo mounted at root."""
    try:
        import gradio as gr
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
    except ImportError as exc:
        raise RuntimeError(
            "Install the website demo with: python -m pip install -r requirements-website-demo.lock"
        ) from exc

    service = FastAPI(
        title="DCFA development workflow demo",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @service.get("/healthz", include_in_schema=False)
    def healthz():
        return JSONResponse(
            {
                "status": "ok",
                "service": "dcfa-development-workflow-demo",
                "version": __version__,
                "evidence_status": "development_only",
                "backend": "daily_selection",
                "default_mode": fixed_analysis_mode or "api_preferred",
                "supported_modes": [fixed_analysis_mode]
                if fixed_analysis_mode
                else ["api_preferred", "api_only", "v2_only"],
                "model": MANAGED_MODEL_PATH,
                "llm_provider": "google_gemini_developer_api",
                "llm_model": GEMINI_MODEL,
            },
            headers={"Cache-Control": "no-store"},
        )

    output_root = output_root_from_environment().resolve()

    @service.get("/readyz", include_in_schema=False)
    def readyz():
        output_ready = output_root_is_writable(output_root)
        try:
            credential = read_managed_token_file(managed_token_file_from_environment())
            del credential
        except (DCFAError, OSError, ValueError):
            managed_credential_ready = False
        else:
            managed_credential_ready = True
        try:
            credential = read_gemini_api_key(gemini_api_key_file_from_environment())
            del credential
            gemini_credential_ready = True
        except (DCFAError, OSError, ValueError):
            gemini_credential_ready = False
        try:
            validate_website_gemini_config()
            gemini_config_ready = True
        except (DCFAError, OSError, ValueError):
            gemini_config_ready = False
        ready = (
            output_ready
            and managed_credential_ready
            and gemini_credential_ready
            and gemini_config_ready
        )
        return JSONResponse(
            {
                "status": "ready" if ready else "not_ready",
                "output_root_writable": output_ready,
                "managed_credential_ready": managed_credential_ready,
                "gemini_credential_ready": gemini_credential_ready,
                "gemini_config_ready": gemini_config_ready,
                "evidence_status": "development_only",
            },
            status_code=200 if ready else 503,
            headers={"Cache-Control": "no-store"},
        )

    @service.middleware("http")
    async def security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    return gr.mount_gradio_app(
        service,
        build_app(
            output_root=output_root,
            fixed_analysis_mode=fixed_analysis_mode,
            presentation_title=presentation_title,
            local_csv_dialogue=local_csv_dialogue,
        ),
        path="/",
        footer_links=[],
        allowed_paths=[str(output_root)],
        show_error=False,
        enable_monitoring=False,
        max_file_size="1mb",
        theme=build_demo_theme(),
        css=DEMO_CSS,
    )


def run_service(**app_options) -> None:
    """Run one process; Gradio serializes the bounded analysis queue."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "Install the website demo with: python -m pip install -r requirements-website-demo.lock"
        ) from exc

    host = os.environ.get("DCFA_SERVER_NAME", "127.0.0.1")
    port = int(os.environ.get("PORT", "7860"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535.")
    require_available_port(host, port)
    uvicorn.run(
        build_service(**app_options),
        host=host,
        port=port,
        workers=1,
        access_log=os.environ.get("DCFA_ACCESS_LOG", "0") == "1",
    )
