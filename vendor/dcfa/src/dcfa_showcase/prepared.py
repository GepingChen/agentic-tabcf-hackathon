"""Freeze, export, and independently verify the public prepared DCFA replay."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from dcfa.artifact_validation import verify_run_directory
from dcfa.canonical import file_sha256, sha256_digest
from dcfa.constants import (
    EstimatorBackend,
    EvidenceStatus,
    ExecutionProfile,
    SupportStatus,
    Track,
    WarningSeverity,
)
from dcfa.evidence import EvidenceLedger
from dcfa.provenance import dcfa_source_tree_hash
from dcfa.schemas import (
    DiagnosticBundle,
    EvidenceRecord,
    QueryResult,
    ResultBundle,
    SupportAssessment,
    WarningRecord,
)
from dcfa.tabcf_iv.managed_client import (
    MANAGED_BACKEND_PARAMETERS,
    MANAGED_CLIENT_PROTOCOL_VERSION,
    MANAGED_CLIENT_VERSION,
    MANAGED_MODEL_PATH,
    MANAGED_SERVICE_PACKAGE_VERSION,
)
from dcfa_website_demo.app import SCENARIOS
from dcfa_website_demo.csv_upload import (
    STANDARD_DEMO_ROWS,
    STANDARD_DEMO_SEED,
    export_standard_demo_csv,
    load_authorized_csv,
)
from dcfa_website_demo.gemini import (
    GEMINI_MODEL,
    PROTOCOL_VERSION,
    validate_website_gemini_config,
)
from dcfa_website_demo.presentation import (
    answer_sentence,
    display_value,
    present_query,
    render_visitor_plot,
)

PREPARED_DEMO_ID = "prepared_demo_v1"
_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "evaluation/configs"
PREPARED_GEMINI_CONFIGS = {
    "website_demo_gemini_v1": _CONFIG_ROOT / "website_demo_gemini_v1.json",
    "website_demo_gemini_v2": _CONFIG_ROOT / "website_demo_gemini_v2.json",
}
MANIFEST_SCHEMA = "dcfa_prepared_demo_manifest_v1"
VISITOR_SCHEMA = "dcfa_prepared_visitor_v1"
VERIFICATION_SCHEMA = "dcfa_prepared_verification_v1"
PROMPT_FILENAME = "prepared_prompt.txt"
CSV_FILENAME = "prepared_demo.csv"
VISITOR_FILENAME = "visitor_result.json"
PLOT_FILENAME = "visitor_plot.png"
SUMMARY_FILENAME = "verification_summary.json"
MANIFEST_FILENAME = "prepared_demo_manifest.json"
PREPARED_PROMPT = SCENARIOS["strong_iv"].question
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_PRIVATE_PATTERN = re.compile(
    r"(?:/Users/|\\Users\\|tabpfn_sk_|AIza[0-9A-Za-z_-]{12,}|"
    r"\b(?:evidence|bundle|specification|trace)_[0-9a-f]{12,}\b)"
)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid prepared-demo JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Prepared-demo JSON must contain an object: {path.name}")
    return payload


def freeze_prepared_demo(directory: Path, *, release_commit: str) -> dict[str, Any]:
    """Create the immutable v1 prompt, synthetic CSV, and pre-run manifest."""
    root = Path(directory)
    if root.exists():
        raise FileExistsError(f"Refusing to overwrite prepared demo directory: {root}")
    if not _COMMIT_PATTERN.fullmatch(release_commit):
        raise ValueError("The DCFA release commit must be a full lowercase Git SHA.")
    root.mkdir(parents=True)
    prompt_path = root / PROMPT_FILENAME
    prompt_path.write_text(f"{PREPARED_PROMPT}\n", encoding="utf-8")
    csv_path = export_standard_demo_csv(root / CSV_FILENAME)
    gemini_config_hash = validate_website_gemini_config()
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "prepared_demo_id": PREPARED_DEMO_ID,
        "dcfa_release_commit": release_commit,
        "dcfa_source_tree_hash": dcfa_source_tree_hash(),
        "input": {
            "prompt_file": PROMPT_FILENAME,
            "prompt_sha256": file_sha256(prompt_path),
            "csv_file": CSV_FILENAME,
            "csv_sha256": file_sha256(csv_path),
            "row_count": STANDARD_DEMO_ROWS,
            "seed": STANDARD_DEMO_SEED,
            "roles": {"outcome": "Y", "treatment": "X", "instrument": "Z"},
            "baseline_covariates": [],
            "treatment_type": "continuous",
            "intervention_labels": ["low", "center", "high"],
        },
        "gemini_profile": {
            "profile_id": PROTOCOL_VERSION,
            "profile_sha256": gemini_config_hash,
            "model": GEMINI_MODEL,
            "request_limit": 1,
            "data_rows_sent": 0,
            "actual_intervention_values_sent": 0,
        },
        "managed_tabpfn_profile": {
            "profile_id": MANAGED_CLIENT_PROTOCOL_VERSION,
            "profile_sha256": sha256_digest(dict(MANAGED_BACKEND_PARAMETERS)),
            "client_version": MANAGED_CLIENT_VERSION,
            "expected_service_package_version": MANAGED_SERVICE_PACKAGE_VERSION,
            "model": MANAGED_MODEL_PATH,
            "thinking_mode": False,
            "fallback": None,
        },
        "public_projection": {
            "schema_version": VISITOR_SCHEMA,
            "required_stage_count": 4,
            "required_disclosure": (
                "This replays a previously executed and independently verified workflow. "
                "No API call is made."
            ),
            "numeric_source": "validated_result_bundle_only",
            "unknown_content_behavior": "suppress_numeric_result",
        },
        "required_run_behavior": {
            "status": "completed",
            "query_count": 1,
            "development_boundary_preserved": True,
            "warning_preservation_required": True,
            "no_prompt_csv_or_seed_tuning_after_run": True,
        },
    }
    _write_json(root / MANIFEST_FILENAME, manifest)
    return manifest


def _validate_manifest(root: Path) -> dict[str, Any]:
    manifest = _load_json(root / MANIFEST_FILENAME)
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("Unsupported prepared-demo manifest schema.")
    if manifest.get("prepared_demo_id") != PREPARED_DEMO_ID:
        raise ValueError("Unexpected prepared-demo identity.")
    if not _COMMIT_PATTERN.fullmatch(str(manifest.get("dcfa_release_commit", ""))):
        raise ValueError("Prepared-demo release commit is invalid.")
    if manifest.get("dcfa_source_tree_hash") != dcfa_source_tree_hash():
        raise ValueError("Prepared-demo manifest does not match the current DCFA source tree.")
    input_contract = manifest.get("input")
    if not isinstance(input_contract, dict):
        raise ValueError("Prepared-demo input contract is missing.")
    prompt_path = root / PROMPT_FILENAME
    csv_path = root / CSV_FILENAME
    if input_contract.get("prompt_sha256") != file_sha256(prompt_path):
        raise ValueError("Prepared prompt hash mismatch.")
    if input_contract.get("csv_sha256") != file_sha256(csv_path):
        raise ValueError("Prepared CSV hash mismatch.")
    if prompt_path.read_text(encoding="utf-8") != f"{PREPARED_PROMPT}\n":
        raise ValueError("Prepared prompt bytes no longer match the frozen v1 question.")
    if input_contract.get("row_count") != STANDARD_DEMO_ROWS:
        raise ValueError("Prepared CSV row contract changed.")
    if input_contract.get("seed") != STANDARD_DEMO_SEED:
        raise ValueError("Prepared synthetic seed changed.")
    profile_id = manifest.get("gemini_profile", {}).get("profile_id")
    if not isinstance(profile_id, str):
        raise ValueError("Prepared Gemini profile is missing.")
    profile_path = PREPARED_GEMINI_CONFIGS.get(profile_id)
    if profile_path is None:
        raise ValueError("Prepared Gemini profile is unsupported.")
    prepared_config_hash = validate_website_gemini_config(
        profile_path,
        expected_version=profile_id,
    )
    if manifest.get("gemini_profile", {}).get("profile_sha256") != prepared_config_hash:
        raise ValueError("Prepared Gemini profile hash mismatch.")
    if manifest.get("managed_tabpfn_profile", {}).get("profile_sha256") != sha256_digest(
        dict(MANAGED_BACKEND_PARAMETERS)
    ):
        raise ValueError("Prepared managed-TabPFN profile hash mismatch.")
    return manifest


def _warning(payload: dict[str, Any]) -> WarningRecord:
    return WarningRecord(
        code=str(payload["code"]),
        message=str(payload["message"]),
        severity=WarningSeverity(str(payload["severity"])),
        source=str(payload["source"]),
    )


def _query(payload: dict[str, Any]) -> QueryResult:
    return QueryResult(
        query_id=str(payload["query_id"]),
        claim_type=str(payload["claim_type"]),
        value_raw=float(payload["value_raw"]),
        value_display=str(payload["value_display"]),
        units=str(payload["units"]),
        support_status=SupportStatus(str(payload["support_status"])),
        warnings=tuple(_warning(item) for item in payload["warnings"]),
        evidence_id=str(payload["evidence_id"]),
    )


def _bundle(payload: dict[str, Any]) -> ResultBundle:
    diagnostics = payload["diagnostics"]
    return ResultBundle(
        result_bundle_id=str(payload["result_bundle_id"]),
        run_id=str(payload["run_id"]),
        specification_id=str(payload["specification_id"]),
        dataset_hash=str(payload["dataset_hash"]),
        track=Track(str(payload["track"])),
        execution_profile=ExecutionProfile(str(payload["execution_profile"])),
        estimator_backend=EstimatorBackend(str(payload["estimator_backend"])),
        evidence_status=EvidenceStatus(str(payload["evidence_status"])),
        x_grid=tuple(float(value) for value in payload["x_grid"]),
        y_grid=tuple(float(value) for value in payload["y_grid"]),
        interventional_cdf=tuple(
            tuple(float(value) for value in row) for row in payload["interventional_cdf"]
        ),
        interventional_mean=tuple(float(value) for value in payload["interventional_mean"]),
        quantile_levels=tuple(float(value) for value in payload["quantile_levels"]),
        interventional_quantiles=tuple(
            tuple(float(value) for value in row) for row in payload["interventional_quantiles"]
        ),
        risk_thresholds=tuple(float(value) for value in payload["risk_thresholds"]),
        interventional_risks=tuple(
            tuple(float(value) for value in row) for row in payload["interventional_risks"]
        ),
        diagnostics=DiagnosticBundle(
            first_stage_f=float(diagnostics["first_stage_f"]),
            first_stage_r2=float(diagnostics["first_stage_r2"]),
            control_rank_cvm=float(diagnostics["control_rank_cvm"]),
            control_rank_mean=float(diagnostics["control_rank_mean"]),
            residual_dependence_score=float(diagnostics["residual_dependence_score"]),
            interpretation=str(diagnostics["interpretation"]),
        ),
        support=tuple(
            SupportAssessment(
                x=float(item["x"]),
                status=SupportStatus(str(item["status"])),
                coverage_score=float(item["coverage_score"]),
                recommended_interval=tuple(float(value) for value in item["recommended_interval"]),
                strict_interval=tuple(float(value) for value in item["strict_interval"]),
                reason=str(item["reason"]),
            )
            for item in payload["support"]
        ),
        warnings=tuple(_warning(item) for item in payload["warnings"]),
        assumptions=tuple(str(value) for value in payload["assumptions"]),
        queries=tuple(_query(item) for item in payload["queries"]),
        source_artifact=str(payload["source_artifact"]),
        source_artifact_hash=str(payload["source_artifact_hash"]),
        cached=bool(payload.get("cached", False)),
    )


def _evidence(payload: dict[str, Any]) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=str(payload["evidence_id"]),
        track=Track(str(payload["track"])),
        evidence_status=EvidenceStatus(str(payload["evidence_status"])),
        estimator_backend=EstimatorBackend(str(payload["estimator_backend"])),
        execution_profile=ExecutionProfile(str(payload["execution_profile"])),
        run_id=str(payload["run_id"]),
        dataset_hash=str(payload["dataset_hash"]),
        specification_id=str(payload["specification_id"]),
        result_bundle_id=str(payload["result_bundle_id"]),
        claim_type=str(payload["claim_type"]),
        value_raw=float(payload["value_raw"]),
        value_display=str(payload["value_display"]),
        units=str(payload["units"]),
        support_status=SupportStatus(str(payload["support_status"])),
        warnings=tuple(_warning(item) for item in payload["warnings"]),
        source_artifact=str(payload["source_artifact"]),
        source_artifact_hash=str(payload["source_artifact_hash"]),
    )


def _load_ledger(path: Path) -> EvidenceLedger:
    records: list[EvidenceRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("Prepared source evidence contains a non-object record.")
            records.append(_evidence(payload))
    return EvidenceLedger(records)


def _csv_preview(path: Path, *, rows: int = 5) -> list[dict[str, float]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        return [
            {name: float(value) for name, value in record.items()}
            for _, record in zip(range(rows), reader, strict=False)
        ]


def export_prepared_showcase(directory: Path, *, source_run_directory: Path) -> dict[str, Any]:
    """Project one independently verified full run into public-safe static files."""
    root = Path(directory)
    manifest = _validate_manifest(root)
    output_paths = [root / VISITOR_FILENAME, root / PLOT_FILENAME, root / SUMMARY_FILENAME]
    if any(path.exists() for path in output_paths):
        raise FileExistsError("Refusing to overwrite a previously exported prepared showcase.")
    source_root = Path(source_run_directory).resolve(strict=True)
    source_verification = verify_run_directory(source_root)
    if source_verification.get("status") != "valid":
        raise ValueError("The full prepared run did not pass independent verification.")
    bundle_payload = _load_json(source_root / "result_bundle.json")
    dataset_payload = _load_json(source_root / "dataset_manifest.json")
    backend_payload = _load_json(source_root / "backend_manifest.json")
    gemini_payload = _load_json(source_root / "gemini_compilation.json")
    bundle = _bundle(bundle_payload)
    ledger = _load_ledger(source_root / "evidence_records.jsonl")
    if (
        bundle.track is not Track.TABCF_IV
        or bundle.execution_profile is not ExecutionProfile.LOCAL_DEVELOPMENT
        or bundle.estimator_backend is not EstimatorBackend.TABPFN
        or bundle.evidence_status is not EvidenceStatus.DEVELOPMENT_ONLY
    ):
        raise ValueError("Prepared source run has an unsupported evidence identity.")
    if len(bundle.queries) != 1:
        raise ValueError("Prepared source run must contain exactly one validated query.")
    uploaded = load_authorized_csv(
        root / CSV_FILENAME,
        outcome="Y",
        treatment="X",
        instrument="Z",
        confirmed=True,
    )
    if dataset_payload.get("dataset_hash") != uploaded.manifest.dataset_hash:
        raise ValueError("Prepared CSV does not match the verified run dataset.")
    if dataset_payload.get("row_count") != STANDARD_DEMO_ROWS:
        raise ValueError("Prepared run row count does not match the frozen input.")
    backend_parameters = backend_payload.get("parameters")
    if not isinstance(backend_parameters, list):
        raise ValueError("Prepared run has no managed-backend parameters.")
    observed_backend_parameters = {
        str(item[0]): str(item[1])
        for item in backend_parameters
        if isinstance(item, list) and len(item) == 2
    }
    if any(
        observed_backend_parameters.get(name) != value for name, value in MANAGED_BACKEND_PARAMETERS
    ):
        raise ValueError("Prepared run does not use the frozen managed-TabPFN profile.")
    if gemini_payload.get("protocol_version") != manifest["gemini_profile"]["profile_id"]:
        raise ValueError("Prepared run does not use the frozen Gemini profile.")
    if gemini_payload.get("data_rows_sent_to_gemini") != 0:
        raise ValueError("Prepared run sent data rows to Gemini.")
    if gemini_payload.get("actual_intervention_values_sent_to_gemini") != 0:
        raise ValueError("Prepared run sent actual intervention values to Gemini.")
    if gemini_payload.get("model_request_count") != 1:
        raise ValueError("Prepared run did not preserve the one-request Gemini contract.")
    proposal = gemini_payload.get("proposal")
    query = bundle.queries[0]
    presented = present_query(query)
    if not presented.allow_numeric:
        raise ValueError("Prepared query is not approved for visitor display.")
    if not isinstance(proposal, dict):
        raise ValueError("Prepared run has no validated symbolic proposal.")
    answer = answer_sentence(query, proposal)
    render_visitor_plot(bundle, ledger, root / PLOT_FILENAME)
    visitor = {
        "schema_version": VISITOR_SCHEMA,
        "prepared_demo_id": PREPARED_DEMO_ID,
        "release": {
            "dcfa_commit": manifest["dcfa_release_commit"],
            "dcfa_source_sha256": manifest["dcfa_source_tree_hash"],
        },
        "disclosure": manifest["public_projection"]["required_disclosure"],
        "question": (root / PROMPT_FILENAME).read_text(encoding="utf-8").rstrip("\n"),
        "data": {
            "source": "Redistributable synthetic continuous-treatment IV example",
            "row_count": STANDARD_DEMO_ROWS,
            "roles": {
                "Y": "Continuous outcome",
                "X": "Continuous treatment",
                "Z": "Scalar instrument",
            },
            "preview": _csv_preview(root / CSV_FILENAME),
        },
        "stages": [
            {"label": "Understand the question", "status": "Completed"},
            {"label": "Check the data", "status": "Completed"},
            {"label": "Run the analysis", "status": "Completed"},
            {"label": "Verify the result", "status": "Completed"},
        ],
        "result": {
            "answer": answer,
            "claim_title": presented.claim.title,
            "value_raw": query.value_raw,
            "value_display": presented.value_display,
            "units": presented.units,
            "support": {
                "title": presented.support.title,
                "explanation": presented.support.explanation,
            },
            "warnings": [
                {
                    "title": warning.title,
                    "explanation": warning.explanation,
                    "action": warning.action,
                    "severity": warning.severity,
                }
                for warning in presented.warnings
            ],
        },
        "development_boundary": (
            "Synthetic, local-development demonstration using managed TabPFN. It is not "
            "locked Track T evidence, proof of IV validity, or production causal advice."
        ),
        "plot": {
            "file": PLOT_FILENAME,
            "alt": (
                "Two-panel verified synthetic result: estimated outcome distributions and "
                "mean and quantile summaries across supported treatment levels."
            ),
        },
    }
    _write_json(root / VISITOR_FILENAME, visitor)
    release_material = {
        "prepared_demo_manifest_sha256": file_sha256(root / MANIFEST_FILENAME),
        "prepared_prompt_sha256": file_sha256(root / PROMPT_FILENAME),
        "prepared_csv_sha256": file_sha256(root / CSV_FILENAME),
        "visitor_result_sha256": file_sha256(root / VISITOR_FILENAME),
        "visitor_plot_sha256": file_sha256(root / PLOT_FILENAME),
        "source_run_manifest_sha256": file_sha256(source_root / "run_manifest.json"),
    }
    summary = {
        "schema_version": VERIFICATION_SCHEMA,
        "prepared_demo_id": PREPARED_DEMO_ID,
        "status": "valid",
        "dcfa_release_commit": manifest["dcfa_release_commit"],
        "verified_at_utc": gemini_payload.get("observed_at_utc"),
        "release_sha256": sha256_digest(release_material),
        "asset_hashes": release_material,
        "checks": [
            "full_artifact_independently_verified",
            "raw_value_matches_evidence_before_display_rounding",
            "warning_and_support_projection_preserved",
            "prepared_prompt_csv_and_profiles_match_frozen_manifest",
            "public_projection_contains_no_credentials_or_private_paths",
        ],
    }
    _write_json(root / SUMMARY_FILENAME, summary)
    return verify_prepared_showcase(root)


def _public_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def verify_prepared_showcase(directory: Path) -> dict[str, Any]:
    """Verify the committed public projection without network or provider construction."""
    root = Path(directory)
    manifest = _validate_manifest(root)
    visitor = _load_json(root / VISITOR_FILENAME)
    summary = _load_json(root / SUMMARY_FILENAME)
    if visitor.get("schema_version") != VISITOR_SCHEMA:
        raise ValueError("Unsupported prepared visitor schema.")
    if summary.get("schema_version") != VERIFICATION_SCHEMA or summary.get("status") != "valid":
        raise ValueError("Prepared verification summary is invalid.")
    if visitor.get("prepared_demo_id") != PREPARED_DEMO_ID:
        raise ValueError("Prepared visitor identity mismatch.")
    result = visitor.get("result")
    if not isinstance(result, dict):
        raise ValueError("Prepared visitor result is missing.")
    raw_value = float(result.get("value_raw"))
    if result.get("value_display") != display_value(raw_value):
        raise ValueError("Prepared visitor rounding does not match the verified raw value.")
    expected_hashes = {
        "prepared_demo_manifest_sha256": file_sha256(root / MANIFEST_FILENAME),
        "prepared_prompt_sha256": file_sha256(root / PROMPT_FILENAME),
        "prepared_csv_sha256": file_sha256(root / CSV_FILENAME),
        "visitor_result_sha256": file_sha256(root / VISITOR_FILENAME),
        "visitor_plot_sha256": file_sha256(root / PLOT_FILENAME),
    }
    asset_hashes = summary.get("asset_hashes")
    if not isinstance(asset_hashes, dict):
        raise ValueError("Prepared verification asset hashes are missing.")
    for name, expected in expected_hashes.items():
        if asset_hashes.get(name) != expected:
            raise ValueError(f"Prepared public asset hash mismatch: {name}")
    release_material = dict(asset_hashes)
    if summary.get("release_sha256") != sha256_digest(release_material):
        raise ValueError("Prepared release hash mismatch.")
    if summary.get("dcfa_release_commit") != manifest.get("dcfa_release_commit"):
        raise ValueError("Prepared release identity mismatch.")
    public_payload = {"visitor": visitor, "summary": summary}
    match = _PRIVATE_PATTERN.search(_public_text(public_payload))
    if match:
        raise ValueError("Prepared public projection contains forbidden private or audit content.")
    return {
        "status": "valid",
        "prepared_demo_id": PREPARED_DEMO_ID,
        "dcfa_release_commit": manifest["dcfa_release_commit"],
        "release_sha256": summary["release_sha256"],
        "value_raw": raw_value,
        "value_display": result["value_display"],
    }
