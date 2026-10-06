"""Canonical serialization and stable content identifiers."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def to_primitive(value: Any) -> Any:
    """Convert supported typed objects into deterministic JSON-compatible values."""
    if dataclasses.is_dataclass(value):
        return {
            field.name: to_primitive(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, np.ndarray):
        return to_primitive(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): to_primitive(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("Canonical JSON does not permit non-finite floating-point values.")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported canonical value type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        to_primitive(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


def is_sha256_digest(value: str) -> bool:
    return bool(_SHA256_PATTERN.fullmatch(str(value)))


def content_id(prefix: str, value: Any, *, length: int = 24) -> str:
    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return f"{prefix}_{digest[:length]}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def dataset_sha256(columns: Mapping[str, np.ndarray]) -> str:
    """Hash named numeric columns without depending on platform object serialization."""
    digest = hashlib.sha256()
    for name in sorted(columns):
        values = np.ascontiguousarray(np.asarray(columns[name], dtype="<f8").reshape(-1))
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(values.shape).encode("ascii"))
        digest.update(b"\0")
        digest.update(values.tobytes(order="C"))
    return f"sha256:{digest.hexdigest()}"
