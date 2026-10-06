"""Deterministic provenance for the exact local DCFA Python source tree."""

from __future__ import annotations

import hashlib
from pathlib import Path


def dcfa_source_tree_hash() -> str:
    """Hash relative paths and bytes for every shipped DCFA Python source file."""
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"
