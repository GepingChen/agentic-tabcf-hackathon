"""Explicitly non-paper development fixtures for the local engineering slice."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dcfa.canonical import dataset_sha256
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.schemas import DatasetManifest


@dataclass(frozen=True)
class DevelopmentIVDataset:
    columns: dict[str, np.ndarray]
    manifest: DatasetManifest


def generate_development_iv(
    *,
    n: int = 320,
    seed: int = 20260808,
    instrument_strength: float = 1.6,
    support_shift: float = 0.0,
) -> DevelopmentIVDataset:
    """Generate a reproducible no-W triangular fixture with no paper-DGP mapping claim."""
    if n < 40:
        raise ValueError("Development IV fixtures require at least 40 rows.")
    rng = np.random.default_rng(seed)
    z = rng.uniform(-1.0, 1.0, size=n)
    latent_h = rng.normal(size=n)
    x_noise = rng.normal(scale=0.45, size=n)
    y_noise = rng.normal(scale=0.6, size=n)
    x = instrument_strength * z + 0.8 * latent_h + x_noise + float(support_shift)
    y = 0.8 + 1.4 * x + 0.25 * x**2 + 0.9 * latent_h + y_noise
    columns = {"Z": z.astype(float), "X": x.astype(float), "Y": y.astype(float)}
    digest = dataset_sha256(columns)
    manifest = DatasetManifest(
        dataset_id=f"dataset_{digest.split(':', maxsplit=1)[1][:24]}",
        dataset_hash=digest,
        source="generated_by_dcfa.tabcf_iv.development_dgp.generate_development_iv",
        source_kind="synthetic_development_fixture",
        row_count=n,
        columns=("Z", "X", "Y"),
        generation_seed=seed,
        dgp_label="dcfa_development_triangular_iv_v1",
        dgp_mapping_status="not_mapped_to_tabcf_manuscript_codes",
        license_note="Generated locally; no external data license applies.",
        track=Track.TABCF_IV,
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
    )
    return DevelopmentIVDataset(columns=columns, manifest=manifest)
