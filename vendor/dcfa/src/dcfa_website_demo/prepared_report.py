"""Display the curated cigarette report without providers or statistical execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ASSET_ROOT = Path(__file__).with_name("assets") / "cigarette_v1"


@dataclass(frozen=True)
class PreparedReport:
    report: str
    warnings: str
    appendix: str
    plot: Path
    csv: Path
    archive: Path
    metadata: dict[str, object]


def load_prepared_report(root: Path = ASSET_ROOT) -> PreparedReport:
    """Read public, release-reviewed files; never fit or contact a provider."""
    names = (
        "report.md",
        "interventional_summary.png",
        "cigarette_144.csv",
        "report.zip",
        "metadata.json",
    )
    if any(not (root / name).is_file() for name in names):
        raise ValueError("The saved example report is unavailable. No analysis was started.")
    report = (root / "report.md").read_text(encoding="utf-8")
    body, appendix = report.split("<details>", 1)
    appendix, warnings = appendix.split("</details>", 1)
    body = "\n".join(line for line in body.splitlines() if not line.startswith(("![", "# Agentic")))
    appendix = appendix.replace("<summary>Technical appendix and evidence index</summary>", "")
    metadata = json.loads((root / names[4]).read_text(encoding="utf-8"))
    for key in ("saved_at_utc", "source_commit"):
        if not isinstance(metadata.get(key), str):
            raise ValueError("The saved example metadata is incomplete.")
    return PreparedReport(
        report=body.strip(),
        warnings=warnings.strip(),
        appendix=appendix.strip(),
        plot=root / names[1],
        csv=root / names[2],
        archive=root / names[3],
        metadata=metadata,
    )


def render_prepared_report() -> None:
    """Create a read-only report tab with no event handlers or conversation state."""
    import gradio as gr

    gr.Markdown(
        "## Cigarette demand: what does the tool deliver?\n\n"
        "A saved report from a real TabPFN run. **No API key or Hugging Face sign-in "
        "is needed to view it; viewing does not rerun the analysis.**\n\n"
        "**Question:** Under the maintained IV assumptions, how does the estimated "
        "distribution of annual cigarette sales per capita change when real price "
        "increases from 100 to 120 CPI-deflated cents per pack?\n\n"
        "**Data:** 144 state-year observations: 48 US states in 1985, 1990 and 1995. "
        "Outcome: log sales per capita; treatment: log real price; instrument: real sales tax. "
        "This exploratory three-column model has no baseline covariates."
    )
    try:
        saved = load_prepared_report()
    except (OSError, ValueError, KeyError):
        gr.Markdown("The saved example report is unavailable. No analysis was started.")
        return
    gr.Image(value=str(saved.plot), interactive=False, show_label=False, elem_id="example-plot")
    gr.Markdown(saved.report, elem_classes="demo-answer")
    with gr.Row():
        gr.DownloadButton("Download demo CSV", value=str(saved.csv))
        gr.DownloadButton("Download full report ZIP", value=str(saved.archive), variant="primary")
    gr.Markdown(
        "The ZIP contains the original report, figure, confirmed analysis plan and numerical "
        "evidence. Open report.md alongside its image in a Markdown viewer.\n\n"
        "[Data source and preparation](https://github.com/GepingChen/DCFA/blob/main/"
        "examples/cigarette_demand_small/SOURCE.md) · "
        "[Data license](https://github.com/GepingChen/DCFA/blob/main/"
        "examples/cigarette_demand_small/GPL-2.0.txt)"
    )
    with gr.Accordion("Technical appendix and run details", open=False):
        gr.Markdown(saved.appendix)
        gr.Markdown(
            f"Run saved: {saved.metadata['saved_at_utc']} · "
            f"Source version: `{saved.metadata['source_commit']}` · "
            "Backend: local TabPFN v2 on HF ZeroGPU."
        )
    gr.HTML(saved.warnings)
