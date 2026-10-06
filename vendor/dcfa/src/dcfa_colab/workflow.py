"""Secret-scoped, notebook-native execution for the bounded DCFA CSV workflow."""

from __future__ import annotations

import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dcfa.artifact_validation import verify_run_directory
from dcfa.errors import DCFAError, ErrorCode
from dcfa_website_demo.app import PortfolioDemoResult, execute_csv_upload
from dcfa_website_demo.csv_upload import load_authorized_csv
from dcfa_website_demo.presentation import answer_sentence, present_query


@dataclass(frozen=True)
class ColabRunResult:
    """Visitor-safe result plus the independently verified downloadable archive."""

    status: str
    visitor_result: dict[str, Any]
    run_directory: Path | None
    archive_path: Path | None
    verification: dict[str, Any] | None


def preflight_colab_csv(
    csv_file: str | Path,
    *,
    outcome: str,
    treatment: str,
    instrument: str,
) -> dict[str, Any]:
    """Validate the bounded local CSV without constructing a provider client."""
    dataset = load_authorized_csv(
        csv_file,
        outcome=outcome,
        treatment=treatment,
        instrument=instrument,
        confirmed=True,
    )
    return {
        "status": "ready_for_explicit_transfer_confirmation",
        "row_count": dataset.manifest.row_count,
        "roles": {
            "outcome": dataset.outcome,
            "treatment": dataset.treatment,
            "instrument": dataset.instrument,
        },
        "column_count": len(dataset.manifest.columns),
    }


def _credential_error(message: str) -> DCFAError:
    return DCFAError(
        ErrorCode.DATA_ACCESS_BLOCKED,
        message,
        stage="colab.credentials",
    )


def _validate_secret_values(gemini_api_key: str, tabpfn_token: str) -> None:
    if (
        not isinstance(gemini_api_key, str)
        or len(gemini_api_key) < 20
        or any(character.isspace() for character in gemini_api_key)
    ):
        raise _credential_error("The DCFA_GEMINI_API_KEY Colab Secret is missing or malformed.")
    if (
        not isinstance(tabpfn_token, str)
        or not tabpfn_token.startswith("tabpfn_sk_")
        or len(tabpfn_token) < 24
        or any(character.isspace() for character in tabpfn_token)
    ):
        raise _credential_error("The DCFA_TABPFN_TOKEN Colab Secret is missing or malformed.")


def _write_secret(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def _scan_run_for_secrets(root: Path, secrets: tuple[str, str]) -> None:
    encoded = tuple(value.encode("utf-8") for value in secrets)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if any(secret in payload for secret in encoded):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "A provider credential reached the run artifact; download is blocked.",
                stage="colab.secret_scan",
            )


def _archive_run(root: Path) -> Path:
    archive = root.with_suffix(".zip")
    if archive.exists():
        raise FileExistsError(f"Refusing to overwrite Colab artifact archive: {archive}")
    with zipfile.ZipFile(archive, mode="x", compression=zipfile.ZIP_DEFLATED) as stream:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                stream.write(path, arcname=path.relative_to(root.parent))
    return archive


def _visitor_result(result: PortfolioDemoResult) -> dict[str, Any]:
    if result.response.status != "completed" or not result.response.queries:
        return {
            "status": "blocked",
            "answer": "No numerical answer is available.",
            "next_action": (
                "Review the displayed input, support, or provider failure and start a new run."
            ),
        }
    query = result.response.queries[0]
    presented = present_query(query)
    if not presented.allow_numeric:
        return {
            "status": "blocked",
            "answer": "No numerical answer is approved for display.",
            "next_action": "Inspect the verified local artifact before using this result.",
        }
    return {
        "status": "completed",
        "answer": answer_sentence(query, result.llm_trace.get("proposal")),
        "support": {
            "title": presented.support.title,
            "explanation": presented.support.explanation,
        },
        "warnings": [
            {
                "title": warning.title,
                "explanation": warning.explanation,
                "action": warning.action,
            }
            for warning in presented.warnings
        ],
        "boundary": (
            "This is a synthetic or user-authorized local-development result using managed "
            "TabPFN. It is not locked Track T evidence or production causal advice."
        ),
    }


def run_colab_analysis(
    *,
    csv_file: str | Path,
    outcome: str,
    treatment: str,
    instrument: str,
    question: str,
    seed: int,
    gemini_api_key: str,
    tabpfn_token: str,
    consent_google_transfer: bool,
    consent_prior_labs_transfer: bool,
    output_root: str | Path,
    client_module: Any | None = None,
    client_version: str | None = None,
    gemini_client: Any | None = None,
    gemini_sdk_version: str | None = None,
) -> ColabRunResult:
    """Execute one confirmed run while keeping both credentials temporary and scoped."""
    _validate_secret_values(gemini_api_key, tabpfn_token)
    if not consent_google_transfer:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "Confirm the question transfer to Google before running.",
            stage="colab.consent.google",
        )
    if not consent_prior_labs_transfer:
        raise DCFAError(
            ErrorCode.DATA_ACCESS_BLOCKED,
            "Confirm the selected Y/X/Z transfer to Prior Labs before running.",
            stage="colab.consent.prior_labs",
        )
    output_path = Path(output_root)
    with tempfile.TemporaryDirectory(prefix="dcfa-colab-credentials-") as temporary:
        secret_root = Path(temporary)
        secret_root.chmod(0o700)
        gemini_path = secret_root / "gemini_api_key"
        tabpfn_path = secret_root / "tabpfn_api_key"
        _write_secret(gemini_path, gemini_api_key)
        _write_secret(tabpfn_path, tabpfn_token)
        result = execute_csv_upload(
            csv_file,
            outcome,
            treatment,
            instrument,
            True,
            seed,
            question=question,
            output_root=output_path,
            token_file=tabpfn_path,
            client_module=client_module,
            client_version=client_version,
            gemini_api_key_file=gemini_path,
            gemini_client=gemini_client,
            gemini_sdk_version=gemini_sdk_version,
        )
    visitor = _visitor_result(result)
    if result.response.status != "completed" or result.output_dir is None:
        return ColabRunResult(
            status="blocked",
            visitor_result=visitor,
            run_directory=None,
            archive_path=None,
            verification=None,
        )
    verification = verify_run_directory(result.output_dir)
    if verification.get("status") != "valid":
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The Colab result did not pass independent artifact verification.",
            stage="colab.verification",
        )
    _scan_run_for_secrets(result.output_dir, (gemini_api_key, tabpfn_token))
    archive = _archive_run(result.output_dir)
    with zipfile.ZipFile(archive) as stream:
        names = stream.namelist()
    if not names or any(name.startswith("/") or ".." in Path(name).parts for name in names):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "The Colab result archive failed its path-safety check.",
            stage="colab.archive",
        )
    return ColabRunResult(
        status="completed",
        visitor_result=visitor,
        run_directory=result.output_dir,
        archive_path=archive,
        verification=verification,
    )


def validate_colab_notebook(path: Path, *, release_commit: str | None = None) -> dict[str, Any]:
    """Statically validate the committed notebook without importing Colab or providers."""
    try:
        notebook = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("The Colab notebook is unavailable or invalid JSON.") from exc
    if notebook.get("nbformat") != 4 or not isinstance(notebook.get("cells"), list):
        raise ValueError("The Colab notebook does not use the supported nbformat contract.")
    cells = notebook["cells"]
    for cell in cells:
        if cell.get("cell_type") == "code":
            if cell.get("outputs") != [] or cell.get("execution_count") is not None:
                raise ValueError("Committed Colab code cells must not contain saved output.")
    text = "\n".join("".join(cell.get("source", [])) for cell in cells)
    required = (
        "DCFA_GEMINI_API_KEY",
        "DCFA_TABPFN_TOKEN",
        "consent_google_transfer",
        "consent_prior_labs_transfer",
        "run_colab_analysis",
        "files.download",
        "Disconnect and delete runtime",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise ValueError(f"The Colab notebook is missing required workflow markers: {missing}")
    forbidden = ("share=True", "ngrok", "cloudflared", "drive.mount", "/Users/", "ssh ")
    observed = [marker for marker in forbidden if marker in text]
    if observed:
        raise ValueError(
            f"The Colab notebook contains forbidden service or local-path content: {observed}"
        )
    commit_match = re.search(r'DCFA_RELEASE_COMMIT\s*=\s*"([0-9a-f]{40})"', text)
    if commit_match is None:
        raise ValueError("The Colab notebook does not pin a full DCFA release commit.")
    observed_commit = commit_match.group(1)
    if release_commit is not None and observed_commit != release_commit:
        raise ValueError("The Colab notebook release commit does not match the approved release.")
    return {
        "status": "valid",
        "release_commit": observed_commit,
        "code_cell_count": sum(cell.get("cell_type") == "code" for cell in cells),
    }
