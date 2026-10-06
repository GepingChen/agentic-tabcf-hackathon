"""Minimal deterministic CLI for the local TabCF Analyst development slice."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from dcfa.agent.benchmark import (
    benchmark_summary,
    load_benchmark_cases,
    run_recorded_benchmark,
)
from dcfa.agent.gemini_live import (
    DEFAULT_MANIFEST_PATH,
    run_gemini_live_smoke,
    verify_gemini_live_smoke,
)
from dcfa.artifact_validation import verify_agent_benchmark_file, verify_run_directory
from dcfa.canonical import file_sha256, to_primitive
from dcfa.errors import DCFAError
from dcfa.hillstrom_policy.contracts import HillstromPolicySpecification, PolicyObjective
from dcfa.hillstrom_policy.data import generate_development_rct, make_stratified_split
from dcfa.hillstrom_policy.pipeline import HillstromPolicyEngine
from dcfa.hillstrom_policy.semisynthetic_pipeline import run_semisynthetic_benchmark
from dcfa.output import require_absent_output_file
from dcfa.tabcf_iv.development_dgp import generate_development_iv
from dcfa.tabcf_iv.development_evaluation import run_development_evaluation
from dcfa.tabcf_iv.development_specification import development_specification
from dcfa.tabcf_iv.fulton import load_fulton_csv
from dcfa.tabcf_iv.locked_runtime import (
    load_locked_runtime_manifest,
    validate_current_runtime,
)
from dcfa.tabcf_iv.managed_smoke import run_managed_agent_smoke
from dcfa.tabcf_iv.pipeline import TabCFAnalysisEngine


def _atomic_write_text(path: Path, payload: str) -> None:
    require_absent_output_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _run_demo(args: argparse.Namespace) -> int:
    strength = 0.02 if args.scenario == "weak_iv" else 1.6
    dataset = generate_development_iv(n=args.rows, seed=args.seed, instrument_strength=strength)
    x_values = tuple(
        float(value) for value in np.quantile(dataset.columns["X"], [0.1, 0.3, 0.5, 0.7, 0.9])
    )
    if args.scenario == "support_violation":
        x_values = (*x_values[:-1], float(np.max(dataset.columns["X"]) + 5.0))
    baseline_covariates = ("W1",) if args.scenario == "nonempty_w" else ()
    treatment_type = "categorical" if args.scenario == "unsupported_treatment" else "continuous"
    specification = development_specification(
        dataset_hash=dataset.manifest.dataset_hash,
        x_values=x_values,
        outcome_threshold=float(np.median(dataset.columns["Y"])),
        seed=args.seed,
        baseline_covariates=baseline_covariates,
        treatment_type=treatment_type,
    )
    if args.scenario == "support_violation":
        specification = replace(
            specification,
            queries=(
                specification.queries[0],
                replace(specification.queries[1], x=x_values[-1]),
                specification.queries[2],
            ),
        )
    try:
        run = TabCFAnalysisEngine().analyze(
            dataset.columns,
            specification,
            dataset.manifest,
            output_dir=args.output_dir,
        )
    except DCFAError as exc:
        print(json.dumps({"status": "blocked", "error": exc.to_dict()}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "run_id": run.bundle.run_id,
                "result_bundle_id": run.bundle.result_bundle_id,
                "execution_profile": run.bundle.execution_profile.value,
                "estimator_backend": run.bundle.estimator_backend.value,
                "evidence_status": run.bundle.evidence_status.value,
                "backend_fit_calls": run.backend_fit_calls,
                "queries": [to_primitive(query) for query in run.bundle.queries],
                "artifacts": {name: str(path) for name, path in run.artifact_paths},
            },
            sort_keys=True,
        )
    )
    return 0


def _run_fulton(args: argparse.Namespace) -> int:
    try:
        dataset = load_fulton_csv(
            args.data_path,
            exact_source=args.exact_source,
            retrieval_date=args.retrieval_date,
            license_note=args.license_note,
        )
        x_values = tuple(
            float(value) for value in np.quantile(dataset.columns["X"], [0.1, 0.3, 0.5, 0.7, 0.9])
        )
        specification = development_specification(
            dataset_hash=dataset.manifest.dataset_hash,
            x_values=x_values,
            outcome_threshold=float(np.median(dataset.columns["Y"])),
            seed=args.seed,
        )
        run = TabCFAnalysisEngine().analyze(
            dataset.columns,
            specification,
            dataset.manifest,
            output_dir=args.output_dir,
        )
    except DCFAError as exc:
        print(json.dumps({"status": "blocked", "error": exc.to_dict()}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "data_label": "fulton_real_application_without_oracle",
                "track": run.bundle.track.value,
                "execution_profile": run.bundle.execution_profile.value,
                "estimator_backend": run.bundle.estimator_backend.value,
                "evidence_status": run.bundle.evidence_status.value,
                "run_id": run.bundle.run_id,
                "result_bundle_id": run.bundle.result_bundle_id,
                "evidence_count": len(run.ledger.records()),
                "artifacts": {name: str(path) for name, path in run.artifact_paths},
            },
            sort_keys=True,
        )
    )
    return 0


def _probe_tabpfn(args: argparse.Namespace) -> int:
    """Run the risky native imports once in a bounded child process."""
    require_absent_output_file(args.output)
    probe = (
        "import importlib.metadata as m; "
        "import torch; import tabpfn; "
        "print('torch=' + m.version('torch')); "
        "print('tabpfn=' + m.version('tabpfn'))"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
        )
        result = {
            "status": "available" if completed.returncode == 0 else "unavailable",
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "timeout_seconds": args.timeout,
            "fallback_attempted": False,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "status": "timeout",
            "returncode": None,
            "stdout": (exc.stdout or "").strip(),
            "stderr": (exc.stderr or "").strip(),
            "timeout_seconds": args.timeout,
            "fallback_attempted": False,
        }
    if args.output is not None:
        _atomic_write_text(
            args.output,
            json.dumps(result, indent=2, sort_keys=True) + "\n",
        )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "available" else 3


def _validate_tabpfn_runtime(manifest_path: Path) -> int:
    try:
        runtime = load_locked_runtime_manifest(manifest_path)
        result = validate_current_runtime(runtime, manifest_path)
    except DCFAError as exc:
        print(json.dumps({"status": "invalid", "error": exc.to_dict()}, sort_keys=True))
        return 5
    print(json.dumps(result, sort_keys=True))
    return 0


def _run_managed_agent_smoke(args: argparse.Namespace) -> int:
    result = run_managed_agent_smoke(
        token_file=args.token_file,
        output_dir=args.output_dir,
    )
    response = result.response
    run = result.run
    payload = {
        "status": response.status,
        "track": "tabcf_iv",
        "data_label": "fixed_synthetic_managed_client_smoke",
        "final_state": response.final_state.value,
        "tool_calls": response.tool_calls,
        "retry_count": response.retry_count,
        "api_prediction_calls": result.api_prediction_calls,
        "usage_before": result.usage_before,
        "usage_after": result.usage_after,
        "queries": [to_primitive(query) for query in response.queries],
        "warnings": [to_primitive(warning) for warning in response.warnings],
        "state_events": [to_primitive(event) for event in response.state_events],
        "error": response.error,
        "run_id": None if run is None else run.bundle.run_id,
        "result_bundle_id": None if run is None else run.bundle.result_bundle_id,
        "backend_fit_calls": None if run is None else run.backend_fit_calls,
        "artifacts": (
            {} if run is None else {name: str(path) for name, path in run.artifact_paths}
        ),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if response.status == "completed" else 2


def _run_gemini_agent_smoke(args: argparse.Namespace) -> int:
    result = run_gemini_live_smoke(
        api_key_file=args.api_key_file,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
    )
    payload = {
        "status": result.response.status,
        "track": "agent_benchmark",
        "data_label": "fixed_synthetic_gemini_live_smoke",
        "trace_id": result.trace_id,
        "interaction_id": result.interaction_id,
        "model_request_count": 1,
        "latency_ms": result.latency_ms,
        "usage": to_primitive(result.usage),
        "list_price_estimate_usd": result.list_price_estimate_usd,
        "run_id": result.run.bundle.run_id,
        "result_bundle_id": result.run.bundle.result_bundle_id,
        "queries": [to_primitive(query) for query in result.response.queries],
        "warnings": [to_primitive(warning) for warning in result.response.warnings],
        "trace_path": str(result.trace_path),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


def _verify_gemini_agent_smoke(output_dir: Path, manifest_path: Path) -> int:
    try:
        result = verify_gemini_live_smoke(output_dir, manifest_path=manifest_path)
    except DCFAError as exc:
        print(json.dumps({"status": "invalid", "error": exc.to_dict()}, sort_keys=True))
        return 4
    print(json.dumps(to_primitive(result), sort_keys=True))
    return 0


def _run_hillstrom_demo(args: argparse.Namespace) -> int:
    dataset = generate_development_rct(n=args.rows, seed=args.seed)
    split = make_stratified_split(dataset, seed=args.seed)
    specification = HillstromPolicySpecification(
        dataset_hash=dataset.manifest.dataset_hash,
        split_manifest_id=split.split_manifest_id,
        objective=PolicyObjective(),
        capacity_fraction=args.capacity,
        seed=args.seed,
    )
    try:
        run = HillstromPolicyEngine().analyze(
            dataset,
            split,
            specification,
            output_dir=args.output_dir,
        )
    except DCFAError as exc:
        print(json.dumps({"status": "blocked", "error": exc.to_dict()}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "track": run.bundle.track.value,
                "execution_profile": run.bundle.execution_profile.value,
                "estimator_backend": run.bundle.estimator_backend.value,
                "evidence_status": run.bundle.evidence_status.value,
                "run_id": run.bundle.run_id,
                "policy_id": run.bundle.policy_id,
                "result_bundle_id": run.bundle.result_bundle_id,
                "test_outcomes_accessed_after_freeze": (run.test_outcomes_accessed_after_freeze),
                "evidence_count": len(run.ledger.records()),
                "artifacts": {name: str(path) for name, path in run.artifact_paths},
            },
            sort_keys=True,
        )
    )
    return 0


def _run_hillstrom_semisynthetic(args: argparse.Namespace) -> int:
    dataset = generate_development_rct(n=args.source_rows, seed=args.seed)
    split = make_stratified_split(dataset, seed=args.seed)
    run = run_semisynthetic_benchmark(
        dataset,
        split,
        replications=args.replications,
        row_count=args.rows_per_replication,
        seed=args.seed,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "track": run.bundle.track.value,
                "execution_profile": run.bundle.execution_profile.value,
                "estimator_backend": run.bundle.estimator_backend.value,
                "evidence_status": run.bundle.evidence_status.value,
                "data_label": run.bundle.data_label,
                "scenario_count": 4,
                "replications_per_scenario": args.replications,
                "evidence_count": len(run.ledger.records()),
                "run_id": run.bundle.run_id,
                "result_bundle_id": run.bundle.result_bundle_id,
                "artifacts": {name: str(path) for name, path in run.artifact_paths},
            },
            sort_keys=True,
        )
    )
    return 0


def _run_track_t_development_evaluation(args: argparse.Namespace) -> int:
    seeds = tuple(int(value) for value in args.seeds.split(",") if value.strip())
    run = run_development_evaluation(
        seeds=seeds,
        rows=args.rows,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "track": run.bundle.track.value,
                "execution_profile": run.bundle.execution_profile.value,
                "estimator_backend": run.bundle.estimator_backend.value,
                "evidence_status": run.bundle.evidence_status.value,
                "data_label": run.bundle.data_label,
                "seed_count": len(seeds),
                "scenario_count": 2,
                "evidence_count": len(run.ledger.records()),
                "run_id": run.bundle.run_id,
                "result_bundle_id": run.bundle.result_bundle_id,
                "artifacts": {name: str(path) for name, path in run.artifact_paths},
            },
            sort_keys=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dcfa", description="DCFA deterministic local tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    from dcfa.tabcf_iv.model_comparison import cli as comparison_cli

    comparison = subparsers.add_parser(
        "compare-tabpfn", help="Run the five-seed development v2 versus 3.5 comparison."
    )
    comparison.add_argument("--output-dir", type=Path, required=True)
    comparison.add_argument("--resume", action="store_true")
    comparison.add_argument("--source-ref", help="Git commit for both statistical runtimes.")
    comparison.set_defaults(handler=comparison_cli)
    demo = subparsers.add_parser("tabcf-demo", help="Run the no-W development-only vertical slice.")
    demo.add_argument(
        "--scenario",
        choices=(
            "strong_iv",
            "weak_iv",
            "support_violation",
            "nonempty_w",
            "unsupported_treatment",
        ),
        default="strong_iv",
    )
    demo.add_argument("--rows", type=int, default=320)
    demo.add_argument("--seed", type=int, default=20260808)
    demo.add_argument("--output-dir", type=Path, required=True)
    demo.set_defaults(handler=_run_demo)

    fulton = subparsers.add_parser(
        "fulton-local",
        help="Run a development-only Fulton workflow from a provenance-recorded local CSV.",
    )
    fulton.add_argument("--data-path", type=Path, required=True)
    fulton.add_argument("--exact-source", required=True)
    fulton.add_argument("--retrieval-date", required=True)
    fulton.add_argument("--license-note", required=True)
    fulton.add_argument("--seed", type=int, default=20260808)
    fulton.add_argument("--output-dir", type=Path, required=True)
    fulton.set_defaults(handler=_run_fulton)

    track_t_evaluation = subparsers.add_parser(
        "track-t-development-evaluation",
        help="Run oracle metrics for the development fallback; this is not TabCF evidence.",
    )
    track_t_evaluation.add_argument("--rows", type=int, default=320)
    track_t_evaluation.add_argument("--seeds", default="101,202,303")
    track_t_evaluation.add_argument("--output-dir", type=Path, required=True)
    track_t_evaluation.set_defaults(handler=_run_track_t_development_evaluation)

    hillstrom = subparsers.add_parser(
        "hillstrom-demo",
        help="Run the synthetic development-only Track H vertical slice.",
    )
    hillstrom.add_argument("--rows", type=int, default=1800)
    hillstrom.add_argument("--seed", type=int, default=20260808)
    hillstrom.add_argument("--capacity", type=float, default=None)
    hillstrom.add_argument("--output-dir", type=Path, required=True)
    hillstrom.set_defaults(handler=_run_hillstrom_demo)

    semisynthetic = subparsers.add_parser(
        "hillstrom-semisynthetic",
        help="Run four development-only known-oracle Track H DGPs.",
    )
    semisynthetic.add_argument("--source-rows", type=int, default=1800)
    semisynthetic.add_argument("--rows-per-replication", type=int, default=1200)
    semisynthetic.add_argument("--replications", type=int, default=50)
    semisynthetic.add_argument("--seed", type=int, default=20260808)
    semisynthetic.add_argument("--output-dir", type=Path, required=True)
    semisynthetic.set_defaults(handler=_run_hillstrom_semisynthetic)

    probe = subparsers.add_parser(
        "tabpfn-probe",
        help="Probe torch/TabPFN in a bounded child process.",
    )
    probe.add_argument("--timeout", type=float, default=20.0)
    probe.add_argument("--output", type=Path, default=None)
    probe.set_defaults(handler=_probe_tabpfn)

    runtime = subparsers.add_parser(
        "validate-tabpfn-runtime",
        help="Fail closed unless the host matches a frozen remote TabPFN manifest.",
    )
    runtime.add_argument("manifest", type=Path)
    runtime.set_defaults(handler=lambda args: _validate_tabpfn_runtime(args.manifest))

    managed_smoke = subparsers.add_parser(
        "managed-agent-smoke",
        help=(
            "Run one development-only typed-agent call over a fixed synthetic "
            "TabPFN Client scenario."
        ),
    )
    managed_smoke.add_argument(
        "--token-file",
        type=Path,
        default=Path("~/.config/dcfa/tabpfn_api_key"),
    )
    managed_smoke.add_argument("--output-dir", type=Path, required=True)
    managed_smoke.set_defaults(handler=_run_managed_agent_smoke)

    gemini_smoke = subparsers.add_parser(
        "gemini-agent-smoke",
        help=(
            "Run one Track A Gemini compile call over a fixed synthetic development-only analysis."
        ),
    )
    gemini_smoke.add_argument(
        "--api-key-file",
        type=Path,
        default=Path("~/.config/dcfa/gemini_api_key"),
    )
    gemini_smoke.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    gemini_smoke.add_argument("--output-dir", type=Path, required=True)
    gemini_smoke.set_defaults(handler=_run_gemini_agent_smoke)

    verify_gemini = subparsers.add_parser(
        "verify-gemini-agent-smoke",
        help="Verify a saved Gemini live smoke without another model or statistical call.",
    )
    verify_gemini.add_argument("output_dir", type=Path)
    verify_gemini.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    verify_gemini.set_defaults(
        handler=lambda args: _verify_gemini_agent_smoke(args.output_dir, args.manifest),
    )

    verify = subparsers.add_parser(
        "verify-artifacts",
        help="Verify hashes, markers, evidence, and report provenance without fitting.",
    )
    verify.add_argument("run_directory", type=Path)
    verify.set_defaults(
        handler=lambda args: _verify_artifacts(args.run_directory),
    )

    benchmark = subparsers.add_parser(
        "agent-benchmark",
        help="Run the frozen recorded Track A workflow benchmark.",
    )
    benchmark.add_argument(
        "--cases",
        type=Path,
        default=Path("evaluation/agent_benchmark/cases/track_a_cases_v1.json"),
    )
    benchmark.add_argument("--output", type=Path, default=None)
    benchmark.add_argument("--runs", type=int, default=5)
    benchmark.set_defaults(
        handler=lambda args: _run_agent_benchmark(args.cases, args.output, args.runs),
    )
    verify_benchmark = subparsers.add_parser(
        "verify-agent-benchmark",
        help="Recompute and verify a recorded Track A benchmark file without rerunning tools.",
    )
    verify_benchmark.add_argument("benchmark_file", type=Path)
    verify_benchmark.add_argument(
        "--cases",
        type=Path,
        default=Path("evaluation/agent_benchmark/cases/track_a_cases_v1.json"),
    )
    verify_benchmark.set_defaults(
        handler=lambda args: _verify_agent_benchmark(args.benchmark_file, args.cases),
    )
    return parser


def _verify_artifacts(run_directory: Path) -> int:
    try:
        result = verify_run_directory(run_directory)
    except DCFAError as exc:
        print(json.dumps({"status": "invalid", "error": exc.to_dict()}, sort_keys=True))
        return 4
    print(json.dumps(to_primitive(result), sort_keys=True))
    return 0


def _verify_agent_benchmark(benchmark_file: Path, cases_path: Path) -> int:
    try:
        result = verify_agent_benchmark_file(benchmark_file, cases_path)
    except DCFAError as exc:
        print(json.dumps({"status": "invalid", "error": exc.to_dict()}, sort_keys=True))
        return 4
    print(json.dumps(to_primitive(result), sort_keys=True))
    return 0


def _run_agent_benchmark(cases_path: Path, output: Path | None, runs: int) -> int:
    require_absent_output_file(output)
    cases = load_benchmark_cases(cases_path)
    traces = run_recorded_benchmark(cases, repetitions=runs)
    payload = {
        **benchmark_summary(traces),
        "case_version": "track_a_cases_v1",
        "case_file_hash": file_sha256(cases_path),
        "traces": tuple(to_primitive(trace) for trace in traces),
    }
    if output is not None:
        _atomic_write_text(
            output,
            json.dumps(to_primitive(payload), indent=2, sort_keys=True) + "\n",
        )
    print(json.dumps(to_primitive(payload), sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except DCFAError as exc:
        print(json.dumps({"status": "blocked", "error": exc.to_dict()}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
