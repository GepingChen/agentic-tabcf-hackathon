"""Strict local CSV ingress for the development-only website demo."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np

from dcfa.canonical import dataset_sha256
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.schemas import DatasetManifest
from dcfa.tabcf_iv.development_dgp import generate_development_iv

MIN_UPLOAD_ROWS = 120
MAX_UPLOAD_ROWS = 256
MAX_UPLOAD_BYTES = 1_000_000
MIN_CONTINUOUS_VALUES = 20
MAX_COLUMN_NAME_CHARS = 120
STANDARD_DEMO_ROWS = 128
STANDARD_DEMO_SEED = 20260813


class CSVDataBoundary(StrEnum):
    """Explicit destination and consent semantics for uploaded rows."""

    DAILY_SELECTED_POLICY = "daily_selected_policy"
    MANAGED_PRIOR_LABS = "managed_prior_labs"
    HF_ZEROGPU_LOCAL = "hf_zerogpu_local"


@dataclass(frozen=True)
class UploadedIVDataset:
    """Validated Y/X/Z arrays and a development-only provenance manifest."""

    columns: dict[str, np.ndarray]
    manifest: DatasetManifest
    outcome: str
    treatment: str
    instrument: str


@dataclass(frozen=True)
class ValidatedCSVColumns:
    """Authorized numeric CSV columns before causal roles are assigned."""

    columns: dict[str, np.ndarray]
    data_boundary: CSVDataBoundary

    @property
    def header(self) -> tuple[str, str, str]:
        names = tuple(self.columns)
        if len(names) != 3:  # pragma: no cover - constructor is module-private in practice
            raise RuntimeError("Validated CSV columns lost the three-column contract.")
        return names[0], names[1], names[2]


def _role_names(outcome: str, treatment: str, instrument: str) -> tuple[str, str, str]:
    roles = tuple(str(value).strip() for value in (outcome, treatment, instrument))
    if any(not role for role in roles):
        raise ValueError("Outcome Y, treatment X, and instrument Z column names are required.")
    if len(set(roles)) != 3:
        raise ValueError("Outcome Y, treatment X, and instrument Z must map to distinct columns.")
    return roles


def _validate_column_names(header: list[str]) -> None:
    if any(
        len(name) > MAX_COLUMN_NAME_CHARS
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
        for name in header
    ):
        raise ValueError(
            f"CSV column names must be at most {MAX_COLUMN_NAME_CHARS} characters and "
            "contain no control characters."
        )


def require_csv_authorization(
    confirmed: bool,
    data_boundary: CSVDataBoundary,
) -> None:
    """Require explicit authorization before any CSV-backed provider request."""
    if not isinstance(data_boundary, CSVDataBoundary):
        raise ValueError("CSV data boundary must be selected explicitly.")
    if confirmed:
        return
    destination = (
        "Prior Labs transmission"
        if data_boundary is CSVDataBoundary.MANAGED_PRIOR_LABS
        else "the selected model policy and data recipients"
        if data_boundary is CSVDataBoundary.DAILY_SELECTED_POLICY
        else "Hugging Face processing"
    )
    raise ValueError(f"Confirm authorization and {destination} before running uploaded data.")


def read_authorized_csv_columns(
    path: str | Path,
    *,
    confirmed: bool,
    data_boundary: CSVDataBoundary = CSVDataBoundary.MANAGED_PRIOR_LABS,
) -> ValidatedCSVColumns:
    """Validate authorized numeric CSV contents before assigning causal roles."""
    require_csv_authorization(confirmed, data_boundary)
    csv_path = Path(path)
    if not csv_path.is_file():
        raise ValueError("Choose a readable local CSV file before running the workflow.")
    if csv_path.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError(f"CSV files are limited to {MAX_UPLOAD_BYTES // 1_000_000} MB.")

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if header is None:
                raise ValueError("The CSV is empty and has no header row.")
            if any(not name or name != name.strip() for name in header):
                raise ValueError(
                    "CSV headers must be non-empty and have no surrounding whitespace."
                )
            if len(header) != len(set(header)):
                raise ValueError("CSV headers must be unique.")
            _validate_column_names(header)
            if len(header) != 3:
                raise ValueError(
                    "The local demo accepts exactly the three selected Y/X/Z columns; "
                    "remove extra columns instead of silently treating them as W."
                )

            values = {name: [] for name in header}
            for row_number, row in enumerate(reader, start=2):
                if len(row) != len(header):
                    raise ValueError(
                        f"CSV row {row_number} does not match the three-column header."
                    )
                for name, raw_value in zip(header, row, strict=True):
                    if not raw_value.strip():
                        raise ValueError(f"CSV row {row_number}, column {name} is missing.")
                    try:
                        value = float(raw_value)
                    except ValueError as exc:
                        raise ValueError(
                            f"CSV row {row_number}, column {name} is not numeric."
                        ) from exc
                    if not np.isfinite(value):
                        raise ValueError(f"CSV row {row_number}, column {name} is not finite.")
                    values[name].append(value)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(
            "The selected file could not be read as a UTF-8 comma-separated CSV."
        ) from exc

    row_count = len(values[header[0]])
    if not MIN_UPLOAD_ROWS <= row_count <= MAX_UPLOAD_ROWS:
        raise ValueError(
            f"Uploaded CSVs must contain {MIN_UPLOAD_ROWS}–{MAX_UPLOAD_ROWS} data rows."
        )
    arrays = {name: np.asarray(column, dtype=float) for name, column in values.items()}
    for name in header:
        if float(np.ptp(arrays[name])) == 0.0:
            raise ValueError(f"Column {name} is constant.")
    return ValidatedCSVColumns(columns=arrays, data_boundary=data_boundary)


def assign_csv_roles(
    validated: ValidatedCSVColumns,
    *,
    outcome: str,
    treatment: str,
    instrument: str,
) -> UploadedIVDataset:
    """Assign and validate one explicit Y/X/Z mapping on preflighted columns."""
    outcome, treatment, instrument = _role_names(outcome, treatment, instrument)
    arrays = validated.columns
    if set(arrays) != {outcome, treatment, instrument}:
        raise ValueError(
            "The local demo accepts exactly the three selected Y/X/Z columns; "
            "remove extra columns instead of silently treating them as W."
        )
    row_count = len(arrays[outcome])
    for name, role in ((outcome, "outcome Y"), (treatment, "treatment X")):
        if np.unique(arrays[name]).size < MIN_CONTINUOUS_VALUES:
            raise ValueError(
                f"Selected {role} must have at least {MIN_CONTINUOUS_VALUES} distinct values."
            )

    role_columns = {
        instrument: arrays[instrument],
        treatment: arrays[treatment],
        outcome: arrays[outcome],
    }
    digest = dataset_sha256(role_columns)
    if validated.data_boundary is CSVDataBoundary.MANAGED_PRIOR_LABS:
        source = "user_authorized_local_csv_upload"
        license_note = (
            "User confirmed authorization to send the selected Y/X/Z rows to Prior Labs; "
            "source and license were not independently verified."
        )
    elif validated.data_boundary is CSVDataBoundary.DAILY_SELECTED_POLICY:
        source = "user_authorized_daily_csv_upload"
        license_note = (
            "User confirmed the selected daily model policy and its stated data recipients; "
            "see daily_execution.json for the policy and actual attempts. "
            "Source and license were not independently verified."
        )
    else:
        source = "user_authorized_hf_zerogpu_csv_upload"
        license_note = (
            "User confirmed authorization to upload the selected Y/X/Z rows to Hugging Face "
            "for ephemeral local-model processing; source and license were not independently "
            "verified."
        )
    manifest = DatasetManifest(
        dataset_id=f"dataset_{digest.split(':', maxsplit=1)[1][:24]}",
        dataset_hash=digest,
        source=source,
        source_kind=source,
        row_count=row_count,
        columns=(instrument, treatment, outcome),
        generation_seed=None,
        dgp_label=None,
        dgp_mapping_status="not_mapped_to_a_frozen_track_t_protocol",
        license_note=license_note,
        track=Track.TABCF_IV,
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.TABPFN,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
    )
    return UploadedIVDataset(
        columns=role_columns,
        manifest=manifest,
        outcome=outcome,
        treatment=treatment,
        instrument=instrument,
    )


def load_authorized_csv(
    path: str | Path,
    *,
    outcome: str,
    treatment: str,
    instrument: str,
    confirmed: bool,
    data_boundary: CSVDataBoundary = CSVDataBoundary.MANAGED_PRIOR_LABS,
) -> UploadedIVDataset:
    """Load an explicitly authorized, exactly-three-column numeric IV CSV."""
    validated = read_authorized_csv_columns(
        path,
        confirmed=confirmed,
        data_boundary=data_boundary,
    )
    return assign_csv_roles(
        validated,
        outcome=outcome,
        treatment=treatment,
        instrument=instrument,
    )


def export_standard_demo_csv(output_path: Path) -> Path:
    """Create the reproducible strong-IV CSV used by the mentor walkthrough."""
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing demo CSV: {output_path}")
    if not output_path.parent.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {output_path.parent}")
    dataset = generate_development_iv(n=STANDARD_DEMO_ROWS, seed=STANDARD_DEMO_SEED)
    with output_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("Y", "X", "Z"))
        writer.writerows(
            zip(
                dataset.columns["Y"],
                dataset.columns["X"],
                dataset.columns["Z"],
                strict=True,
            )
        )
    return output_path
