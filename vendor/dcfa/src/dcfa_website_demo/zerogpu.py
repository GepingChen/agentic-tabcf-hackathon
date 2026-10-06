"""Authenticated API-first daily analysis with in-process ZeroGPU v2 backup."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import gradio as gr
import spaces
from huggingface_hub import hf_hub_download

from dcfa.artifact_validation import verify_run_directory
from dcfa.canonical import file_sha256
from dcfa.errors import DCFAError, ErrorCode
from dcfa.tabcf_iv.local_tabpfn import (
    LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
    LOCAL_TABPFN_V2_MODEL_FILENAME,
    LOCAL_TABPFN_V2_MODEL_HASH,
    LOCAL_TABPFN_V2_MODEL_REPO,
    LOCAL_TABPFN_V2_MODEL_REVISION,
    make_local_tabpfn_v2_backend,
)
from dcfa_website_demo.app import (
    DEMO_CSS,
    WebsiteFinalizationError,
    _execute_compiled_dataset,
    _execution_error_outputs,
    _input_error_outputs,
    _log_operator_error,
    build_app,
    build_demo_theme,
    execute_local_portfolio_scenario,
    execute_prepared_local_csv,
    format_portfolio_result,
    portfolio_ui_updates,
)
from dcfa_website_demo.upload_cleanup import _safe_unlink_upload as _safe_unlink_upload

DEFAULT_ZEROGPU_OUTPUT_ROOT = Path("/tmp/dcfa-zerogpu-runs")
DEFAULT_GRADIO_TEMP_ROOT = Path("/tmp/gradio")
DEFAULT_SECRET_ROOT = Path("/tmp/dcfa-zerogpu-secrets")


def zerogpu_launch_kwargs() -> dict[str, Any]:
    """Return the shared, fail-closed launch configuration for the Space entrypoint."""
    return {
        "blocked_paths": [str(DEFAULT_ZEROGPU_OUTPUT_ROOT), str(DEFAULT_SECRET_ROOT)],
        "enable_monitoring": False,
        "footer_links": [],
        "max_file_size": "1mb",
        "show_error": False,
        "theme": build_demo_theme(),
        "css": DEMO_CSS,
    }


def resolve_preloaded_model() -> Path:
    """Resolve and hash-check the build-preloaded TabPFN v2 checkpoint."""
    try:
        resolved = Path(
            hf_hub_download(
                repo_id=LOCAL_TABPFN_V2_MODEL_REPO,
                filename=LOCAL_TABPFN_V2_MODEL_FILENAME,
                revision=LOCAL_TABPFN_V2_MODEL_REVISION,
                local_files_only=True,
            )
        ).resolve(strict=True)
    except Exception as exc:
        raise RuntimeError("The frozen TabPFN v2 checkpoint was not preloaded.") from exc
    if file_sha256(resolved) != LOCAL_TABPFN_V2_MODEL_HASH:
        raise RuntimeError("The preloaded TabPFN v2 checkpoint hash does not match.")
    return resolved


def _gemini_secret() -> str | None:
    value = os.environ.get("DCFA_GEMINI_API_KEY")
    if value is None:
        return None
    return _validate_gemini_key(value, "DCFA_GEMINI_API_KEY is malformed.")


def _validate_gemini_key(value: str | None, message: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) < 20
        or any(character.isspace() for character in value)
    ):
        raise ValueError(message)
    return value


def _request_gemini_key(space_secret: str | None, temporary_key: str | None) -> str:
    if space_secret is not None:
        return space_secret
    return _validate_gemini_key(
        temporary_key,
        "Enter a valid temporary Gemini API key for this request.",
    )


@contextmanager
def _temporary_secret_file(secret: str) -> Iterator[Path]:
    secret_parent = Path(os.environ.get("DCFA_SECRET_ROOT", str(DEFAULT_SECRET_ROOT)))
    secret_parent.mkdir(parents=True, exist_ok=True)
    secret_parent.chmod(0o700)
    with tempfile.TemporaryDirectory(
        prefix="request-",
        dir=secret_parent,
    ) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        path = root / "api_key"
        path.write_text(secret, encoding="utf-8")
        path.chmod(0o600)
        yield path


# Keep the existing Gemini call-site name while sharing the secret lifecycle.
_temporary_gemini_file = _temporary_secret_file


def execute_space_api(kwargs: dict, directory: Path, settings: dict):
    from dcfa_website_demo.daily import execute_api_attempt

    secret = os.environ.get("DCFA_TABPFN_API_KEY", "").strip()
    if not secret or any(character.isspace() for character in secret):
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "The Space owner must configure the TabPFN API credential.",
            stage="daily.api.credentials",
        )
    with _temporary_secret_file(secret) as token_file:
        return execute_api_attempt(kwargs, directory, dict(settings, token_file=token_file))


def execute_space_dataset(
    kwargs: dict, *, model_path: Path, prediction_runner, analysis_mode: str = "api_preferred"
):
    from dcfa_website_demo.daily import execute_daily_dataset

    def v2_executor(compiled_kwargs, directory, settings):
        return _execute_compiled_dataset(
            **compiled_kwargs,
            reserved_output_dir=directory,
            preserve_failure=True,
            prediction_runner=prediction_runner,
            backend_parameters=LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
            backend_factory=lambda spec: make_local_tabpfn_v2_backend(spec, model_path=model_path),
        )

    return execute_daily_dataset(
        mode=analysis_mode,
        compiled_kwargs=kwargs,
        managed_settings={},
        api_executor=execute_space_api,
        v2_executor=v2_executor,
        v2_location="Hugging Face Space "
        + os.environ.get("SPACE_ID", "GPChen01/dcfa-zerogpu")
        + " (in-process ZeroGPU)",
    )


def _require_login(profile: gr.OAuthProfile | None) -> None:
    if profile is None:
        raise gr.Error("Sign in with Hugging Face before running this workflow.")


def _scan_for_secret(root: Path, secret: str | None) -> None:
    if secret is None:
        return
    encoded = secret.encode("utf-8")
    for path in root.rglob("*"):
        if path.is_file() and encoded in path.read_bytes():
            raise RuntimeError("A service credential reached the run artifact.")


def _archive_run(root: Path) -> Path:
    archive_root = Path(os.environ.get("GRADIO_TEMP_DIR", str(DEFAULT_GRADIO_TEMP_ROOT)))
    archive_root.mkdir(parents=True, exist_ok=True)
    archive = archive_root / f"{root.name}-{uuid.uuid4().hex[:8]}.zip"
    try:
        with zipfile.ZipFile(archive, mode="x", compression=zipfile.ZIP_DEFLATED) as stream:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    stream.write(path, arcname=path.relative_to(root.parent))
        with zipfile.ZipFile(archive) as stream:
            names = stream.namelist()
        if not names or any(name.startswith("/") or ".." in Path(name).parts for name in names):
            archive.unlink(missing_ok=True)
            raise RuntimeError("The verified run archive failed its path-safety check.")
    except Exception:
        archive.unlink(missing_ok=True)
        raise
    return archive


def _public_plot_copy(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    target_root = Path(os.environ.get("GRADIO_TEMP_DIR", str(DEFAULT_GRADIO_TEMP_ROOT)))
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / f"dcfa-result-{uuid.uuid4().hex}.png"
    try:
        shutil.copy2(path, target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return str(target)


def _verified_projection(result: Any, secret: str | None) -> tuple[Any, ...]:
    archive: Path | None = None
    public_plot: str | None = None
    root = result.output_dir
    if root is not None and "daily_execution" in result.llm_trace:
        root = root.parent
    try:
        formatted = format_portfolio_result(result)
        if result.response.status == "completed" and result.output_dir is not None:
            verification = verify_run_directory(result.output_dir)
            if verification.get("status") != "valid":
                raise RuntimeError("The result did not pass independent artifact verification.")
            public_plot = _public_plot_copy(result.plot_path)
            formatted = (*formatted[:4], public_plot)
        if root is not None:
            _scan_for_secret(root, secret)
            _scan_for_secret(root, os.environ.get("DCFA_TABPFN_API_KEY"))
            # Include the failed API attempt and safe blocked-run records in the download.
            if result.response.status == "completed" or "daily_execution" in result.llm_trace:
                archive = _archive_run(root)
        return portfolio_ui_updates(
            formatted,
            buttons_enabled=True,
            archive_path=str(archive) if archive is not None else None,
        )
    except Exception:
        if public_plot is not None:
            Path(public_plot).unlink(missing_ok=True)
        if archive is not None:
            archive.unlink(missing_ok=True)
        raise
    finally:
        if root is not None and root.is_dir():
            shutil.rmtree(root)


def build_zerogpu_app(*, build_revision: str) -> Any:
    """Build the authenticated canonical or duplicated ZeroGPU application."""
    model_path = resolve_preloaded_model()
    secret = _gemini_secret()
    deployment_mode = "zerogpu_duplicate" if secret is not None else "zerogpu_canonical"
    output_root = Path(
        os.environ.get("DCFA_OUTPUT_ROOT", str(DEFAULT_ZEROGPU_OUTPUT_ROOT))
    ).resolve()

    def authorize(profile: gr.OAuthProfile | None) -> None:
        _require_login(profile)

    def authorize_csv(
        temporary_api_key: str | None,
        profile: gr.OAuthProfile | None,
    ) -> None:
        del temporary_api_key
        _require_login(profile)

    @spaces.GPU(duration=120)
    def gpu_predictions(backend, stage, features, target, prediction_features=None, y_grid=None):
        from dcfa.tabcf_iv.pipeline import predict_backend

        return predict_backend(backend, stage, features, target, prediction_features, y_grid)

    def daily_executor(kwargs, analysis_mode):
        return execute_space_dataset(
            kwargs,
            model_path=model_path,
            prediction_runner=gpu_predictions,
            analysis_mode=analysis_mode,
        )

    def run_scenario(
        scenario: str,
        question: str,
        rows: int,
        seed: int,
        profile: gr.OAuthProfile | None,
        analysis_mode: str = "api_preferred",
    ) -> tuple[Any, ...]:
        _require_login(profile)
        try:
            if secret is None:
                result = execute_local_portfolio_scenario(
                    scenario,
                    rows,
                    seed,
                    question=question,
                    prediction_runner=gpu_predictions,
                    model_path=model_path,
                    dataset_executor=lambda kwargs: daily_executor(kwargs, analysis_mode),
                    output_root=output_root,
                )
            else:
                with _temporary_gemini_file(secret) as secret_file:
                    result = execute_local_portfolio_scenario(
                        scenario,
                        rows,
                        seed,
                        question=question,
                        prediction_runner=gpu_predictions,
                        model_path=model_path,
                        dataset_executor=lambda kwargs: daily_executor(kwargs, analysis_mode),
                        output_root=output_root,
                        gemini_api_key_file=secret_file,
                    )
            return (*_verified_projection(result, secret), gr.update(interactive=True))
        except DCFAError as exc:
            _log_operator_error(exc)
            return (
                *portfolio_ui_updates(_execution_error_outputs(exc), buttons_enabled=True),
                gr.update(interactive=True),
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return (
                *portfolio_ui_updates(_input_error_outputs(str(exc)), buttons_enabled=True),
                gr.update(interactive=True),
            )

    def chat_csv(history, columns, overrides, temporary_key, on_request):
        from dcfa_website_demo.dialogue import compile_csv_turn

        request_secret = _request_gemini_key(secret, temporary_key)
        with _temporary_gemini_file(request_secret) as secret_file:
            return compile_csv_turn(
                history,
                columns,
                overrides,
                api_key_file=secret_file,
                on_request=on_request,
            )

    def run_csv(
        validated,
        compilation,
        seed,
        profile: gr.OAuthProfile | None,
        analysis_mode: str = "api_preferred",
    ):
        _require_login(profile)
        result = execute_prepared_local_csv(
            validated,
            compilation,
            seed,
            prediction_runner=gpu_predictions,
            model_path=model_path,
            dataset_executor=lambda kwargs: daily_executor(kwargs, analysis_mode),
            output_root=output_root,
        )
        try:
            from dcfa_website_demo.dialogue import plan_html

            card = plan_html(compilation)
            if result.output_dir is not None:
                # A separate report appendix preserves the existing statistical report identities.
                (result.output_dir / "confirmed_plan.html").write_text(card, encoding="utf-8")
            projected = list(_verified_projection(result, secret))
            projected[0]["value"] = card + "\n\n" + projected[0].get("value", "")
            projected[0]["visible"] = True
            return tuple(projected)
        except (DCFAError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise WebsiteFinalizationError(str(exc)) from exc
        finally:
            if result.output_dir is not None and result.output_dir.is_dir():
                shutil.rmtree(result.output_dir)

    app = build_app(
        output_root=output_root,
        build_revision=build_revision,
        deployment_mode=deployment_mode,
        space_authorize_handler=authorize,
        space_csv_authorize_handler=authorize_csv,
        space_scenario_handler=run_scenario,
        space_csv_handler=run_csv,
        space_csv_chat_handler=chat_csv,
    )

    def analyze_v2(payload: dict, oauth_token: gr.OAuthToken):
        from dcfa_website_demo.v2_remote import serve_v2

        try:
            return serve_v2(
                payload,
                oauth_token.token,
                model_path=model_path,
                output_root=output_root,
                prediction_runner=gpu_predictions,
            )
        except DCFAError as exc:
            return {"status": "blocked", "code": exc.code.value}, None
        except Exception:
            return {"status": "blocked", "code": "V2_EXECUTION_FAILED"}, None

    register_v2_api(app, analyze_v2)
    return app


def register_v2_api(app, handler):
    """Expose the separately authenticated, whole-analysis API."""
    with app:
        remote_input = gr.JSON(visible=False)
        remote_status = gr.JSON(visible=False)
        remote_archive = gr.File(visible=False)
        remote_button = gr.Button(visible=False)
        remote_button.click(
            handler,
            inputs=remote_input,
            outputs=(remote_status, remote_archive),
            api_name="analyze_v2",
            concurrency_limit=1,
        )
