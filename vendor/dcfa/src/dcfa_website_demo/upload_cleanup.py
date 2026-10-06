"""Upload cleanup shared by local and ZeroGPU interfaces without backend imports."""

from __future__ import annotations

import os
from pathlib import Path


def _safe_unlink_upload(path: str | None) -> None:
    if not path:
        return
    candidate = Path(path).resolve()
    temp_root = Path(os.environ.get("GRADIO_TEMP_DIR", "/tmp/gradio")).resolve()
    if candidate.is_relative_to(temp_root):
        candidate.unlink(missing_ok=True)
