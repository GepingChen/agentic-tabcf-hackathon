"""Fail-closed manifest validation for a remote locked TabPFN execution host."""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dcfa.canonical import file_sha256, is_sha256_digest
from dcfa.errors import DCFAError, ErrorCode
from dcfa.tabcf_iv.backend import UPSTREAM_TABCF_COMMIT


@dataclass(frozen=True)
class LockedTabPFNRuntime:
    protocol_version: str
    python_version: str
    package_versions: tuple[tuple[str, str], ...]
    upstream_source_commit: str
    source_checkout: str
    runtime_image_digest: str
    model_path: str
    model_artifact_hash: str

    def backend_parameters(self, manifest_path: Path) -> tuple[tuple[str, str], ...]:
        model_path = Path(self.model_path)
        if not model_path.is_absolute():
            model_path = manifest_path.parent / model_path
        return (
            ("model_path", str(model_path.resolve())),
            ("model_artifact_hash", self.model_artifact_hash),
            ("runtime_image_digest", self.runtime_image_digest),
        )


def load_locked_runtime_manifest(path: Path) -> LockedTabPFNRuntime:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        packages = payload.pop("package_versions")
        if not isinstance(packages, dict):
            raise TypeError("package_versions must be an object")
        runtime = LockedTabPFNRuntime(
            package_versions=tuple(
                sorted((str(key), str(value)) for key, value in packages.items())
            ),
            **payload,
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Could not load the locked TabPFN runtime manifest.",
            stage="tabpfn.runtime_manifest",
        ) from exc
    serialized = json.dumps(payload, sort_keys=True)
    if "REQUIRED" in serialized or any(
        "REQUIRED" in value for pair in runtime.package_versions for value in pair
    ):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Locked TabPFN runtime manifest still contains REQUIRED placeholders.",
            stage="tabpfn.runtime_manifest",
        )
    required_packages = {"numpy", "scipy", "scikit-learn", "torch", "tabpfn"}
    if set(dict(runtime.package_versions)) != required_packages:
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Locked TabPFN runtime must freeze exactly the required package set.",
            stage="tabpfn.runtime_manifest",
            context={"required_packages": sorted(required_packages)},
        )
    if runtime.upstream_source_commit != UPSTREAM_TABCF_COMMIT:
        raise DCFAError(
            ErrorCode.HASH_MISMATCH,
            "Runtime manifest does not pin the inspected TabCF source commit.",
            stage="tabpfn.runtime_manifest",
        )
    if not is_sha256_digest(runtime.runtime_image_digest) or not is_sha256_digest(
        runtime.model_artifact_hash
    ):
        raise DCFAError(
            ErrorCode.INVALID_SPECIFICATION,
            "Runtime image and model artifact require sha256 digests.",
            stage="tabpfn.runtime_manifest",
        )
    return runtime


def validate_current_runtime(runtime: LockedTabPFNRuntime, manifest_path: Path) -> dict[str, str]:
    failures: dict[str, str] = {}
    observed_python = ".".join(str(value) for value in sys.version_info[:3])
    if observed_python != runtime.python_version:
        failures["python_version"] = f"expected={runtime.python_version},observed={observed_python}"
    for package, expected in runtime.package_versions:
        try:
            observed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            observed = "not-installed"
        if observed != expected:
            failures[f"package:{package}"] = f"expected={expected},observed={observed}"
    configured_digest = os.environ.get("DCFA_RUNTIME_IMAGE_DIGEST", "")
    if configured_digest != runtime.runtime_image_digest:
        failures["runtime_image_digest"] = (
            f"expected={runtime.runtime_image_digest},observed={configured_digest or 'unset'}"
        )
    checkout = Path(runtime.source_checkout)
    if not checkout.is_absolute():
        checkout = manifest_path.parent / checkout
    completed = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    observed_commit = completed.stdout.strip() if completed.returncode == 0 else "unavailable"
    if observed_commit != runtime.upstream_source_commit:
        failures["upstream_source_commit"] = (
            f"expected={runtime.upstream_source_commit},observed={observed_commit}"
        )
    model_path = dict(runtime.backend_parameters(manifest_path))["model_path"]
    model = Path(model_path)
    observed_hash = file_sha256(model) if model.is_file() else "missing"
    if observed_hash != runtime.model_artifact_hash:
        failures["model_artifact_hash"] = (
            f"expected={runtime.model_artifact_hash},observed={observed_hash}"
        )
    if failures:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "Current host does not match the locked TabPFN runtime manifest.",
            stage="tabpfn.runtime_validation",
            context={"failures": failures},
        )
    return {
        "status": "valid",
        "runtime_image_digest": runtime.runtime_image_digest,
        "model_artifact_hash": runtime.model_artifact_hash,
        "upstream_source_commit": runtime.upstream_source_commit,
    }
