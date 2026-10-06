"""Fail-closed guards for immutable, versioned local result paths."""

from __future__ import annotations

from pathlib import Path

from dcfa.errors import DCFAError, ErrorCode


def require_fresh_output_directory(path: Path | None) -> None:
    """Allow an absent or empty directory, but never overwrite prior artifacts."""
    if path is None:
        return
    target = Path(path)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise DCFAError(
            ErrorCode.OUTPUT_PATH_EXISTS,
            "Output path already contains material; choose a new versioned run directory.",
            stage="output.preflight",
            context={"output_path": str(target)},
        )


def require_absent_output_file(path: Path | None) -> None:
    """Reject any existing file-system entry before writing a standalone artifact."""
    if path is None:
        return
    target = Path(path)
    if target.exists():
        raise DCFAError(
            ErrorCode.OUTPUT_PATH_EXISTS,
            "Output path already exists; choose a new versioned artifact filename.",
            stage="output.preflight",
            context={"output_path": str(target)},
        )
