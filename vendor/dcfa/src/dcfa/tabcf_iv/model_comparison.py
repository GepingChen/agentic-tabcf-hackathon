"""Small, resumable development comparison of existing v2 and managed 3.5 paths."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tarfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from dcfa.artifact_validation import verify_run_directory
from dcfa.constants import EstimatorBackend
from dcfa.tabcf_iv.development_dgp import generate_development_iv
from dcfa.tabcf_iv.development_evaluation import _oracle_components
from dcfa.tabcf_iv.estimands import interpolate_risks

SEEDS = tuple(range(20261004, 20261009))
METRICS = ("cdf_rmse", "mean_rmse", "quantile_rmse", "risk_rmse")


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def score_bundle(bundle: dict, threshold: float) -> dict[str, float]:
    oracle = _oracle_components(SimpleNamespace(**bundle), threshold)
    observed = (
        bundle["interventional_cdf"],
        bundle["interventional_mean"],
        bundle["interventional_quantiles"],
        interpolate_risks(bundle["interventional_cdf"], bundle["y_grid"], (threshold,)),
    )
    return {
        metric: float(np.sqrt(np.mean((np.asarray(value) - truth) ** 2)))
        for metric, value, truth in zip(METRICS, observed, oracle, strict=True)
    }


def comparison_kwargs(seed: int, output_root: Path) -> tuple[dict, float]:
    from dcfa_website_demo.gemini import GeminiWebsiteCompilation

    dataset = generate_development_iv(n=128, seed=seed, instrument_strength=1.6)
    manifest = replace(dataset.manifest, estimator_backend=EstimatorBackend.TABPFN)
    interventions = tuple(
        float(x) for x in np.quantile(dataset.columns["X"], [0.3, 0.4, 0.5, 0.6, 0.7])
    )
    compilation = GeminiWebsiteCompilation(
        "Y",
        "X",
        "Z",
        "mean_contrast",
        "high",
        "low",
        None,
        {"model": "none", "model_request_count": 0, "source": "deterministic_model_comparison"},
    )
    return dict(
        result_scenario="model_comparison",
        output_scenario="model-comparison",
        columns=dataset.columns,
        manifest=manifest,
        outcome="Y",
        treatment="X",
        instrument="Z",
        interventions=interventions,
        seed=seed,
        output_root=output_root,
        compilation=compilation,
    ), float(np.median(dataset.columns["Y"]))


def summarize(records: list[dict]) -> dict:
    pairs = []
    for seed in SEEDS:
        arms = {r["model"]: r for r in records if r["seed"] == seed and r["status"] == "completed"}
        if set(arms) != {"api_only", "v2_only"}:
            continue
        a, b = arms["api_only"], arms["v2_only"]
        # Grid equality is ordinary comparability validation, not a new frozen protocol.
        if a["grid"] != b["grid"]:
            pairs.append({"seed": seed, "status": "incomparable_grids"})
            continue
        pairs.append(
            {
                "seed": seed,
                "status": "paired",
                "difference_35_minus_v2": {m: a["metrics"][m] - b["metrics"][m] for m in METRICS},
            }
        )
    paired = [p for p in pairs if p["status"] == "paired"]
    aggregate = {}
    for m in METRICS:
        values = [p["difference_35_minus_v2"][m] for p in paired]
        aggregate[m] = {
            "mean_difference": float(np.mean(values)) if values else None,
            "seed_standard_error": float(np.std(values, ddof=1) / math.sqrt(len(values)))
            if len(values) > 1
            else None,
            "evidence_id": f"comparison:paired:{m}",
            "source_evidence_ids": [
                f"comparison:{p['seed']}:{arm}:{m}"
                for p in paired
                for arm in ("api_only", "v2_only")
            ],
        }
    return {
        "evidence_status": "development_only",
        "track": "tabcf_iv",
        "planned_pairs": len(SEEDS),
        "completed_pairs": len(paired),
        "arms": records,
        "pairs": pairs,
        "aggregate": aggregate,
    }


def render_report(summary: dict) -> str:
    lines = [
        "# TabPFN model comparison (development only)",
        "",
        "Synthetic engineering measurement; not locked Track T evidence or an agent comparison.",
        "One fixed strong-IV DGP, five planned seeds, 128 rows; one estimator per model.",
        "3.5 Thinking is off. Risk is P(Y <= sample median), interpolated from the validated CDF.",
        "Latency includes API/CUDA hosting and queues; it is not intrinsic model speed.",
        "Negative differences favor 3.5. All refusals, failures and missing pairs are retained.",
        "",
        f"Completed pairs: {summary['completed_pairs']}/{summary['planned_pairs']}.",
        "",
        "| Seed | Model | Status | CDF RMSE | Mean RMSE | Quantile RMSE | Risk RMSE | Seconds |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["arms"]:
        metrics = r.get("metrics", {})
        cells = [f"{metrics[m]:.6g}" if m in metrics else "—" for m in METRICS]
        lines.append(
            f"| {r['seed']} | {r['model']} | {r['status']} | "
            + " | ".join(cells)
            + f" | {r.get('client_wall_seconds', '—')} |"
        )
    lines += [
        "",
        "## Paired differences (3.5 minus v2)",
        "",
        "| Metric | Mean difference | Seed SE | Evidence ID in summary.json |",
        "|---|---|---|---|",
    ]
    for metric, row in summary["aggregate"].items():
        lines.append(
            f"| {metric} | {row['mean_difference']} | {row['seed_standard_error']} | "
            f"{row['evidence_id']} |"
        )
    lines += [
        "",
        "Per-arm evidence, model configuration, warnings, usage, status and artifact paths are in "
        "`summary.json` and `seed-*/<mode>/measurement.json`. No confidence or superiority claim "
        "is supported by this small development measurement.",
    ]
    return "\n".join(lines) + "\n"


def run_comparison(
    output_dir: Path,
    *,
    resume: bool = False,
    executor=None,
    source_ref: str | None = None,
) -> dict:
    from dcfa_website_demo.daily import archive_daily_result, execute_daily_dataset

    executor = executor or execute_daily_dataset
    output_dir = output_dir.resolve()
    if output_dir.exists() and not resume:
        raise ValueError("Choose a fresh output directory or explicitly use --resume.")
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = {
        "seeds": list(SEEDS),
        "rows": 128,
        "instrument_strength": 1.6,
        "intervention_quantiles": [0.3, 0.4, 0.5, 0.6, 0.7],
        "quantile_levels": [0.1, 0.5, 0.9],
        "threshold": "sample Y median",
        "models": ["api_only", "v2_only"],
        "evidence_status": "development_only",
    }
    config_path = output_dir / "configuration.json"
    if config_path.exists():
        if json.loads(config_path.read_text()) != plan:
            raise ValueError("Resume configuration differs from the saved comparison.")
    else:
        write_json(config_path, plan)
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        (output_dir / "source_commit.txt").write_text(revision.stdout.strip() + "\n")
    verifier = verify_run_directory
    saved_runtime = output_dir / "runtime_commit.txt"
    if source_ref is None and saved_runtime.exists():
        source_ref = saved_runtime.read_text().strip()
    if source_ref is not None:
        revision = subprocess.check_output(
            ["git", "rev-parse", "--verify", source_ref + "^{commit}"], text=True
        ).strip()
        source = output_dir / "runtime-source"
        identity = output_dir / "runtime_commit.txt"
        if identity.exists() and identity.read_text().strip() != revision:
            raise ValueError("Resume runtime commit differs from the saved run.")
        if not source.exists():
            archive = output_dir / "runtime-source.tar"
            subprocess.run(
                ["git", "archive", "--format=tar", "-o", str(archive), revision, "src"], check=True
            )
            source.mkdir()
            with tarfile.open(archive) as stream:
                stream.extractall(source, filter="data")
            identity.write_text(revision + "\n")
        env = dict(os.environ, PYTHONPATH=str(source / "src"))
        worker = Path(__file__).resolve().parents[2] / "dcfa_website_demo/comparison_worker.py"

        def execute_versioned(*, mode, compiled_kwargs, managed_settings):
            from dcfa_website_demo.v2_remote import make_payload

            directory = compiled_kwargs["output_root"]
            write_json(
                directory / "worker_request.json",
                {
                    "mode": mode,
                    "payload": make_payload(compiled_kwargs),
                },
            )
            with (directory / "worker.log").open("a") as log:
                subprocess.run(
                    [sys.executable, str(worker), str(directory)],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            value = json.loads((directory / "worker_result.json").read_text())
            return SimpleNamespace(
                output_dir=Path(value["output_dir"]),
                response=SimpleNamespace(**value["response"]),
                llm_trace=value["llm_trace"],
            )

        def verify_versioned(directory):
            code = (
                "import sys,json; from pathlib import Path; "
                "from dcfa.artifact_validation import verify_run_directory; "
                "print(json.dumps(verify_run_directory(Path(sys.argv[1]))))"
            )
            verified = subprocess.check_output(
                [sys.executable, "-c", code, str(directory)], env=env
            )
            write_json(directory / "independent_verification.json", json.loads(verified))

        executor = execute_versioned
        verifier = verify_versioned
    records = []
    stopped = False
    for i, seed in enumerate(SEEDS):
        for mode in ("api_only", "v2_only") if i % 2 == 0 else ("v2_only", "api_only"):
            directory = output_dir / f"seed-{seed}" / mode
            record_path = directory / "measurement.json"
            if record_path.exists():
                record = json.loads(record_path.read_text())
                if record["status"] not in ("not_run_quota",):
                    records.append(record)
                    continue
            record = {
                "seed": seed,
                "model": mode,
                "status": "not_run_quota" if stopped else "running",
            }
            directory.mkdir(parents=True, exist_ok=True)
            if (directory / "started.json").exists() and not record_path.exists():
                record["status"] = "interrupted_execution_not_resubmitted"
            if record["status"] == "running":
                write_json(directory / "started.json", record)
                kwargs, threshold = comparison_kwargs(seed, directory)
                print(f"Start {seed} {mode}", flush=True)
                try:
                    result = executor(mode=mode, compiled_kwargs=kwargs, managed_settings={})
                    daily = result.llm_trace["daily_execution"]
                    attempt = daily["attempts"][-1]
                    record.update(
                        status=result.response.status,
                        error=result.response.error,
                        client_wall_seconds=attempt.get("client_wall_seconds"),
                        api_usage=attempt.get("api_usage"),
                        actual_model=daily.get("actual_model"),
                        backend_manifest=daily.get("backend_manifest"),
                        output_dir=str(result.output_dir.relative_to(output_dir)),
                    )
                    if result.response.status == "completed":
                        verifier(result.output_dir)
                        bundle = json.loads((result.output_dir / "result_bundle.json").read_text())
                        metrics = score_bundle(bundle, threshold)
                        record.update(
                            metrics=metrics,
                            threshold=threshold,
                            result_bundle_id=bundle["result_bundle_id"],
                            warnings=bundle["warnings"],
                            grid={
                                key: bundle[key] for key in ("x_grid", "y_grid", "quantile_levels")
                            },
                            evidence={
                                m: {
                                    "evidence_id": f"comparison:{seed}:{mode}:{m}",
                                    "value": v,
                                    "source_bundle_id": bundle["result_bundle_id"],
                                    "source_artifact": record["output_dir"] + "/result_bundle.json",
                                }
                                for m, v in metrics.items()
                            },
                        )
                    archive_daily_result(result)
                    if daily.get("error_code") == "MANAGED_QUOTA_EXHAUSTED":
                        stopped = True
                except Exception as exc:
                    # Provider errors must not leak credentials or response bodies.
                    record.update(status="failed", exception_type=type(exc).__name__)
                print(f"Finish {seed} {mode}: {record['status']}", flush=True)
            write_json(record_path, record)
            records.append(record)
            summary = summarize(records)
            write_json(output_dir / "summary.json", summary)
            (output_dir / "report.md").write_text(render_report(summary))
    return summarize(records)


def cli(args) -> int:
    summary = run_comparison(args.output_dir, resume=args.resume, source_ref=args.source_ref)
    print(json.dumps({"completed_pairs": summary["completed_pairs"], "planned_pairs": len(SEEDS)}))
    return 0 if summary["completed_pairs"] == len(SEEDS) else 2
