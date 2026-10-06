"""Fail-closed Fulton Fish loader for a user-provided, provenance-recorded CSV."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from dcfa.canonical import dataset_sha256, file_sha256
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import DCFAError, ErrorCode
from dcfa.schemas import DatasetManifest
from dcfa.tabcf_iv.development_dgp import DevelopmentIVDataset

FULTON_EXPECTED_ROWS = 97
FULTON_UPSTREAM_URL = "https://vincentarelbundock.github.io/Rdatasets/csv/wooldridge/fish.csv"


def load_fulton_csv(
    path: Path,
    *,
    exact_source: str,
    retrieval_date: str,
    license_note: str,
) -> DevelopmentIVDataset:
    provenance = {
        "exact_source": exact_source,
        "retrieval_date": retrieval_date,
        "license_note": license_note,
    }
    missing_provenance = [name for name, value in provenance.items() if not value.strip()]
    if missing_provenance:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Fulton input requires explicit source, retrieval date, and usage/license note.",
            stage="fulton.provenance",
            context={"missing": missing_provenance},
        )
    try:
        with Path(path).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            rows = tuple(reader)
            column_names = tuple(reader.fieldnames or ())
    except OSError as exc:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Could not read the user-provided Fulton CSV.",
            stage="fulton.data",
        ) from exc
    required = {"lavgprc", "wave2", "ltotqty"}
    missing_columns = sorted(required - set(column_names))
    if missing_columns or len(rows) != FULTON_EXPECTED_ROWS:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Fulton CSV schema or row count does not match the frozen upstream contract.",
            stage="fulton.data",
            context={
                "missing_columns": missing_columns,
                "expected_rows": FULTON_EXPECTED_ROWS,
                "observed_rows": len(rows),
            },
        )
    try:
        columns = {
            "X": np.asarray([float(row["lavgprc"]) for row in rows], dtype=float),
            "Z": np.asarray([float(row["wave2"]) for row in rows], dtype=float),
            "Y": np.asarray([float(row["ltotqty"]) for row in rows], dtype=float),
        }
    except (TypeError, ValueError) as exc:
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Fulton causal-role columns must be numeric.",
            stage="fulton.data",
        ) from exc
    if not all(np.all(np.isfinite(values)) for values in columns.values()):
        raise DCFAError(
            ErrorCode.INVALID_DATA,
            "Fulton causal-role columns contain missing or non-finite values.",
            stage="fulton.data",
        )
    dataset_hash = dataset_sha256(columns)
    manifest = DatasetManifest(
        dataset_id=f"fulton_{dataset_hash.split(':', 1)[1][:24]}",
        dataset_hash=dataset_hash,
        source=exact_source,
        source_kind="real_iv_application_without_oracle",
        row_count=len(rows),
        columns=("Z", "X", "Y"),
        generation_seed=None,
        dgp_label=None,
        dgp_mapping_status="not_applicable_real_data",
        license_note=(
            f"{license_note} Local raw file hash: {file_sha256(Path(path))}. "
            f"Retrieved: {retrieval_date}."
        ),
        track=Track.TABCF_IV,
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
    )
    return DevelopmentIVDataset(columns=columns, manifest=manifest)
