"""Evidence ledger validation and release gates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from numbers import Real
from typing import TYPE_CHECKING

import numpy as np

from dcfa.canonical import content_id, is_sha256_digest
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile, Track
from dcfa.errors import DCFAError, ErrorCode
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.schemas import (
    BackendManifest,
    EvidenceRecord,
    PolicyEvaluationBundle,
    ResultBundle,
    SemiSyntheticEvaluationBundle,
    TrackTDevelopmentEvaluationBundle,
)

if TYPE_CHECKING:
    from dcfa.hillstrom_policy.contracts import FrozenPolicyArtifact, HillstromDataManifest


def build_evidence_record(**fields: object) -> EvidenceRecord:
    provisional = EvidenceRecord(evidence_id="pending", **fields)  # type: ignore[arg-type]
    evidence_id = content_id("evidence", replace(provisional, evidence_id=""))
    return replace(provisional, evidence_id=evidence_id)


class EvidenceLedger:
    """In-memory content-addressed ledger with strict duplicate semantics."""

    def __init__(self, records: Iterable[EvidenceRecord] = ()) -> None:
        self._records: dict[str, EvidenceRecord] = {}
        for record in records:
            self.add(record)

    def add(self, record: EvidenceRecord) -> None:
        required_text = (
            record.claim_type,
            record.value_display,
            record.units,
            record.source_artifact,
        )
        if (
            not isinstance(record.value_raw, Real)
            or isinstance(record.value_raw, bool)
            or not np.isfinite(record.value_raw)
            or any(not isinstance(value, str) or not value.strip() for value in required_text)
            or not is_sha256_digest(record.dataset_hash)
            or not is_sha256_digest(record.source_artifact_hash)
        ):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Evidence records require finite values, explicit labels, and exact hashes.",
                stage="evidence.add",
            )
        expected_id = content_id("evidence", replace(record, evidence_id=""))
        if record.evidence_id != expected_id:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                "Evidence record content does not match its content-addressed ID.",
                stage="evidence.add",
                context={"expected": expected_id, "observed": record.evidence_id},
            )
        existing = self._records.get(record.evidence_id)
        if existing is not None and existing != record:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                f"Evidence ID {record.evidence_id} resolved to conflicting records.",
                stage="evidence.add",
            )
        self._records[record.evidence_id] = record

    def resolve(self, evidence_id: str) -> EvidenceRecord:
        try:
            return self._records[evidence_id]
        except KeyError as exc:
            raise DCFAError(
                ErrorCode.EVIDENCE_NOT_FOUND,
                f"Evidence ID {evidence_id} was not found.",
                stage="evidence.resolve",
                context={"evidence_id": evidence_id},
            ) from exc

    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))


def validate_evidence_record(
    record: EvidenceRecord,
    bundle: (
        ResultBundle
        | PolicyEvaluationBundle
        | SemiSyntheticEvaluationBundle
        | TrackTDevelopmentEvaluationBundle
    ),
) -> None:
    expected = {
        "track": (record.track, bundle.track),
        "evidence_status": (record.evidence_status, bundle.evidence_status),
        "estimator_backend": (record.estimator_backend, bundle.estimator_backend),
        "execution_profile": (record.execution_profile, bundle.execution_profile),
        "run_id": (record.run_id, bundle.run_id),
        "dataset_hash": (record.dataset_hash, bundle.dataset_hash),
        "specification_id": (record.specification_id, bundle.specification_id),
        "result_bundle_id": (record.result_bundle_id, bundle.result_bundle_id),
        "source_artifact": (record.source_artifact, bundle.source_artifact),
        "source_artifact_hash": (record.source_artifact_hash, bundle.source_artifact_hash),
    }
    mismatches = [name for name, (left, right) in expected.items() if left != right]
    if mismatches:
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            f"Evidence record does not match its result bundle: {mismatches}.",
            stage="evidence.validation",
            context={"mismatches": mismatches, "evidence_id": record.evidence_id},
        )
    if record.support_status.value == "unsupported":
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Unsupported interventions cannot produce numerical causal evidence.",
            stage="evidence.validation",
            context={"evidence_id": record.evidence_id},
        )


def validate_bundle_evidence(bundle: ResultBundle, ledger: EvidenceLedger) -> None:
    _validate_exact_evidence_mapping(
        tuple(query.evidence_id for query in bundle.queries),
        bundle.result_bundle_id,
        ledger,
    )
    for query in bundle.queries:
        record = ledger.resolve(query.evidence_id)
        validate_evidence_record(record, bundle)
        query_fields = {
            "claim_type": (record.claim_type, query.claim_type),
            "value_raw": (record.value_raw, query.value_raw),
            "value_display": (record.value_display, query.value_display),
            "units": (record.units, query.units),
            "support_status": (record.support_status, query.support_status),
            "warnings": (record.warnings, query.warnings),
        }
        mismatches = [name for name, (left, right) in query_fields.items() if left != right]
        if mismatches:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                f"Query {query.query_id} does not match evidence {record.evidence_id}.",
                stage="evidence.validation",
                context={"mismatches": mismatches},
            )


def _validate_exact_evidence_mapping(
    estimate_ids: tuple[str, ...],
    result_bundle_id: str,
    ledger: EvidenceLedger,
) -> None:
    records = ledger.records()
    record_ids = tuple(record.evidence_id for record in records)
    if len(estimate_ids) != len(set(estimate_ids)) or set(estimate_ids) != set(record_ids):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Result estimates and evidence ledger must have a one-to-one ID mapping.",
            stage="evidence.validation",
        )
    if any(record.result_bundle_id != result_bundle_id for record in records):
        raise DCFAError(
            ErrorCode.EVIDENCE_MISMATCH,
            "Evidence ledger contains a record for a different result bundle.",
            stage="evidence.validation",
        )


def validate_policy_bundle_evidence(
    bundle: PolicyEvaluationBundle,
    ledger: EvidenceLedger,
) -> None:
    estimates = (*bundle.values, *bundle.contrasts, *bundle.experimental_effects)
    _validate_exact_evidence_mapping(
        tuple(estimate.evidence_id for estimate in estimates),
        bundle.result_bundle_id,
        ledger,
    )
    for estimate in estimates:
        record = ledger.resolve(estimate.evidence_id)
        validate_evidence_record(record, bundle)
        if hasattr(estimate, "baseline_policy_name"):
            expected_claim_type = (
                f"paired_policy_contrast:{estimate.policy_name}:minus:"
                f"{estimate.baseline_policy_name}:{estimate.method}"
            )
        elif hasattr(estimate, "outcome"):
            expected_claim_type = (
                f"randomized_arm_effect:{estimate.outcome}:{estimate.action}:minus:"
                f"{estimate.baseline_action}"
            )
        else:
            expected_claim_type = f"policy_value:{estimate.policy_name}:{estimate.method}"
        if (
            record.claim_type != expected_claim_type
            or record.value_raw != estimate.value_raw
            or record.value_display != estimate.value_display
            or record.units != estimate.units
            or record.support_status.value != "supported"
        ):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                f"Policy estimate does not match evidence {record.evidence_id}.",
                stage="evidence.validation",
            )
        if record.warnings != bundle.warnings:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                f"Policy estimate {record.evidence_id} did not preserve bundle warnings.",
                stage="evidence.validation",
            )


def validate_semisynthetic_bundle_evidence(
    bundle: SemiSyntheticEvaluationBundle,
    ledger: EvidenceLedger,
) -> None:
    _validate_exact_evidence_mapping(
        tuple(estimate.evidence_id for estimate in bundle.values),
        bundle.result_bundle_id,
        ledger,
    )
    for estimate in bundle.values:
        record = ledger.resolve(estimate.evidence_id)
        validate_evidence_record(record, bundle)
        if (
            record.claim_type
            != f"semisynthetic:{estimate.scenario}:{estimate.metric}:replication_mean"
            or record.value_raw != estimate.value_raw
            or record.value_display != estimate.value_display
            or record.units != estimate.units
            or record.support_status.value != "supported"
        ):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                f"Semi-synthetic estimate does not match evidence {record.evidence_id}.",
                stage="evidence.validation",
            )
        if record.warnings != bundle.warnings:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                f"Semi-synthetic evidence {record.evidence_id} lost warnings.",
                stage="evidence.validation",
            )


def validate_track_t_development_evidence(
    bundle: TrackTDevelopmentEvaluationBundle,
    ledger: EvidenceLedger,
) -> None:
    _validate_exact_evidence_mapping(
        tuple(estimate.evidence_id for estimate in bundle.values),
        bundle.result_bundle_id,
        ledger,
    )
    for estimate in bundle.values:
        record = ledger.resolve(estimate.evidence_id)
        validate_evidence_record(record, bundle)
        if (
            record.claim_type != f"development_oracle_metric:{estimate.scenario}:{estimate.metric}"
            or record.value_raw != estimate.value_raw
            or record.value_display != estimate.value_display
            or record.units != estimate.units
            or record.support_status.value != "supported"
        ):
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                f"Track T development metric does not match evidence {record.evidence_id}.",
                stage="evidence.validation",
            )
        if record.warnings != bundle.warnings:
            raise DCFAError(
                ErrorCode.EVIDENCE_MISMATCH,
                f"Track T development evidence {record.evidence_id} lost warnings.",
                stage="evidence.validation",
            )


def validate_track_t_release(
    bundle: ResultBundle,
    ledger: EvidenceLedger,
    *,
    headline: bool = True,
    backend_manifest: BackendManifest | None = None,
) -> None:
    """Reject fallback/mock/development evidence from locked Track T outputs."""
    validate_bundle_evidence(bundle, ledger)
    failures: list[str] = []
    if bundle.track is not Track.TABCF_IV:
        failures.append("wrong_track")
    if bundle.execution_profile is not ExecutionProfile.LOCKED_EVALUATION:
        failures.append("not_locked_evaluation")
    if bundle.estimator_backend is not EstimatorBackend.TABPFN:
        failures.append("not_tabpfn")
    if bundle.evidence_status is not EvidenceStatus.ELIGIBLE_FOR_RELEASE:
        failures.append("not_release_eligible")
    if backend_manifest is None:
        failures.append("missing_backend_manifest")
    else:
        backend_markers = (
            backend_manifest.track,
            backend_manifest.execution_profile,
            backend_manifest.estimator_backend,
            backend_manifest.evidence_status,
        )
        bundle_markers = (
            bundle.track,
            bundle.execution_profile,
            bundle.estimator_backend,
            bundle.evidence_status,
        )
        if backend_markers != bundle_markers:
            failures.append("backend_manifest_marker_mismatch")
        if backend_manifest.dcfa_source_tree_hash != dcfa_source_tree_hash():
            failures.append("backend_manifest_source_mismatch")
        if not is_sha256_digest(backend_manifest.model_artifact_hash):
            failures.append("invalid_model_artifact_hash")
        if not is_sha256_digest(backend_manifest.runtime_image_digest):
            failures.append("invalid_runtime_image_digest")
    for record in ledger.records():
        if record.result_bundle_id != bundle.result_bundle_id:
            continue
        if record.estimator_backend in {
            EstimatorBackend.SKLEARN_QUANTILE_FALLBACK,
            EstimatorBackend.MOCK,
        }:
            failures.append(f"forbidden_backend:{record.evidence_id}")
        if record.evidence_status is not EvidenceStatus.ELIGIBLE_FOR_RELEASE:
            failures.append(f"development_evidence:{record.evidence_id}")
    if headline and not bundle.queries:
        failures.append("no_headline_evidence")
    if failures:
        raise DCFAError(
            ErrorCode.RELEASE_GATE_FAILED,
            "Track T release validation failed.",
            stage="release.validation",
            context={"failures": failures},
        )


def validate_track_h_release(
    bundle: PolicyEvaluationBundle,
    ledger: EvidenceLedger,
    dataset_manifest: HillstromDataManifest,
    policy: FrozenPolicyArtifact,
) -> None:
    """Reject synthetic/development/unfrozen material from a real Track H result."""
    validate_policy_bundle_evidence(bundle, ledger)
    failures: list[str] = []
    if bundle.track is not Track.HILLSTROM_POLICY:
        failures.append("wrong_track")
    if bundle.execution_profile is not ExecutionProfile.LOCKED_EVALUATION:
        failures.append("not_locked_evaluation")
    if bundle.estimator_backend is not EstimatorBackend.SKLEARN_POLICY:
        failures.append("wrong_policy_backend")
    if bundle.evidence_status is not EvidenceStatus.ELIGIBLE_FOR_RELEASE:
        failures.append("not_release_eligible")
    if dataset_manifest.source_kind != "real_randomized_experiment":
        failures.append("not_real_randomized_experiment")
    if not all(
        (
            dataset_manifest.exact_source.strip(),
            dataset_manifest.retrieval_date.strip(),
            dataset_manifest.raw_file_hash.strip(),
            dataset_manifest.license_note.strip(),
        )
    ):
        failures.append("incomplete_data_provenance")
    if not is_sha256_digest(dataset_manifest.dataset_hash) or not is_sha256_digest(
        dataset_manifest.raw_file_hash
    ):
        failures.append("invalid_data_hashes")
    if dataset_manifest.dataset_hash != bundle.dataset_hash:
        failures.append("dataset_hash_mismatch")
    if not policy.created_without_test_outcomes:
        failures.append("policy_not_frozen_before_test")
    if policy.policy_id != bundle.policy_id:
        failures.append("policy_id_mismatch")
    if policy.split_manifest_id != bundle.split_manifest_id:
        failures.append("split_id_mismatch")
    policy_markers = (
        policy.track,
        policy.execution_profile,
        policy.estimator_backend,
        policy.evidence_status,
    )
    bundle_markers = (
        bundle.track,
        bundle.execution_profile,
        bundle.estimator_backend,
        bundle.evidence_status,
    )
    if policy.dataset_hash != bundle.dataset_hash or policy_markers != bundle_markers:
        failures.append("policy_bundle_contract_mismatch")
    if failures:
        raise DCFAError(
            ErrorCode.RELEASE_GATE_FAILED,
            "Track H release validation failed.",
            stage="release.validation",
            context={"failures": failures},
        )
