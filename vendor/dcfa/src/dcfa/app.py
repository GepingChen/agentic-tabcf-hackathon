"""Optional local Gradio shell for the public TabCF-only development workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from dcfa.canonical import to_primitive
from dcfa.errors import DCFAError
from dcfa.tabcf_iv.development_dgp import generate_development_iv
from dcfa.tabcf_iv.development_specification import development_specification
from dcfa.tabcf_iv.pipeline import TabCFAnalysisEngine


def run_development_analysis(
    scenario: str,
    rows: int,
    seed: int,
) -> tuple[str, str, str | None]:
    """UI callback; Hillstrom is intentionally absent from this public surface."""
    strength = 0.02 if scenario == "weak_iv" else 1.6
    dataset = generate_development_iv(n=int(rows), seed=int(seed), instrument_strength=strength)
    x_values = tuple(
        float(value) for value in np.quantile(dataset.columns["X"], [0.1, 0.3, 0.5, 0.7, 0.9])
    )
    if scenario == "support_violation":
        x_values = (*x_values[:-1], float(np.max(dataset.columns["X"]) + 5.0))
    specification = development_specification(
        dataset_hash=dataset.manifest.dataset_hash,
        x_values=x_values,
        outcome_threshold=float(np.median(dataset.columns["Y"])),
        seed=int(seed),
    )
    output_root = Path("artifacts/local/ui") / specification.specification_id
    run_index = 1
    output_dir = output_root / f"run-{run_index:04d}"
    while output_dir.exists():
        run_index += 1
        output_dir = output_root / f"run-{run_index:04d}"
    try:
        run = TabCFAnalysisEngine().analyze(
            dataset.columns,
            specification,
            dataset.manifest,
            output_dir=output_dir,
        )
    except DCFAError as exc:
        return (
            "Blocked",
            json.dumps(exc.to_dict(), indent=2, sort_keys=True),
            None,
        )
    rows_out = [
        {
            "query_id": query.query_id,
            "claim_type": query.claim_type,
            "value": query.value_display,
            "units": query.units,
            "evidence_id": query.evidence_id,
            "warnings": [warning.code for warning in query.warnings],
        }
        for query in run.bundle.queries
    ]
    status = (
        "Development-only engineering result. The selected sklearn backend is not TabCF and "
        "is ineligible for Track T claims."
    )
    return (
        status,
        json.dumps(to_primitive(rows_out), indent=2, sort_keys=True),
        str(output_dir / "interventional_summary.png"),
    )


def build_app() -> Any:
    """Import Gradio only when the optional UI is explicitly requested."""
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional UI with: python -m pip install -e '.[ui]'"
        ) from exc

    with gr.Blocks(title="Agentic TabCF development demo") as app:
        gr.Markdown(
            "# Agentic TabCF — local development demo\n"
            "Continuous treatment, scalar IV, continuous outcome, and no baseline covariates W. "
            "The local sklearn fallback validates workflow mechanics only and is not TabCF."
        )
        with gr.Row():
            scenario = gr.Dropdown(
                choices=["strong_iv", "weak_iv", "support_violation"],
                value="strong_iv",
                label="Scenario",
            )
            rows = gr.Slider(120, 1200, value=320, step=20, label="Rows")
            seed = gr.Number(value=20260808, precision=0, label="Seed")
        run_button = gr.Button("Run validated workflow", variant="primary")
        status = gr.Markdown()
        evidence = gr.Code(language="json", label="Evidence-linked query results")
        plot = gr.Image(type="filepath", label="Validated result-bundle plot")
        run_button.click(
            run_development_analysis,
            inputs=(scenario, rows, seed),
            outputs=(status, evidence, plot),
        )
    return app


def main() -> None:
    build_app().launch(inbrowser=False)


if __name__ == "__main__":
    main()
