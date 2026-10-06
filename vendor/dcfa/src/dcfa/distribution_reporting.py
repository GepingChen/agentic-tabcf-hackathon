"""Tables, downloadable projections and plots from one validated distribution bundle."""

from __future__ import annotations

import html
from pathlib import Path

from dcfa.canonical import to_primitive
from dcfa.evidence import validate_bundle_evidence


def export_distribution(bundle, ledger):
    validate_bundle_evidence(bundle, ledger)
    if bundle.distribution is None:
        raise ValueError("No distribution projection is available.")
    return {
        "result_bundle_id": bundle.result_bundle_id,
        "track": bundle.track.value,
        "evidence_status": bundle.evidence_status.value,
        "distribution": bundle.distribution,
        "evidence": {
            q.query_id: to_primitive(ledger.resolve(q.evidence_id)) for q in bundle.queries
        },
        "warnings": to_primitive(bundle.warnings),
        "assumptions": bundle.assumptions,
    }


def distribution_markdown(distribution, queries):
    """Use validated display strings without recalculating headline values."""
    d = distribution
    r = d["request"]
    lookup = {q.query_id: q for q in queries}

    def cell(key):
        display = f"{float(lookup[key].value_raw):.1f}"
        return "0.0" if display == "-0.0" else display

    p0, p1 = r["prices"]
    lines = [
        "### Distributional analysis — Track T · Real data · Exploratory estimates",
        "",
        f"Prices: {p0:g} to {p1:g} {r['treatment_units']}. "
        f"All differences are {p1:g} minus {p0:g}.",
        "",
        (
            "State-year sales per capita; each observation has equal weight."
            if any(
                warning.code == "POOLED_STATE_YEAR_LIMITATIONS"
                for warning in getattr(queries[0], "warnings", ())
            )
            else ""
        ),
        "",
        "**Sales quantiles**",
        "",
        f"Levels and changes are in {r['outcome_units']}. "
        "Each row describes a percentile of the estimated sales distribution; "
        "the median is the 50th percentile.",
        "",
        f"| Quantile | Price {p0:g} | Price {p1:g} | Change ({p1:g} − {p0:g}) |",
        "|:---|---:|---:|---:|",
    ]
    for row in d["quantiles"]:
        if row["level"] not in (0.25, 0.5, 0.75):
            continue
        values = [
            "Not resolved on grid" if limited else cell(key)
            for key, limited in zip(row["values"], row["boundary_limited"], strict=True)
        ]
        change = "Not resolved on grid" if any(row["boundary_limited"]) else cell(row["difference"])
        lines.append(f"| {row['level']:.0%} | {values[0]} | {values[1]} | {change} |")
    if r["threshold"] is not None:
        lines += [
            "",
            "**Probability above the specified sales threshold**",
            "",
            f"Sales strictly exceeding {r['threshold']:g} {r['outcome_units']}. "
            "Levels are percentages; the change is in percentage points.",
            "",
            f"| Price {p0:g} (%) | Price {p1:g} (%) | Change (percentage points) |",
            "|---:|---:|---:|",
            f"| {cell(d['probabilities'][0])} | {cell(d['probabilities'][1])} | "
            f"{cell(d['probability_difference'])} |",
        ]
    return "\n".join(lines)


def distribution_warning_html(bundle, *, boundary=""):
    """Keep all limitations visible at the end, without competing with the results."""
    notes = [warning.message for warning in bundle.warnings]
    notes.extend(bundle.assumptions)
    notes.append(bundle.diagnostics.interpretation)
    notes.append(
        "The PDF is an approximate density from finite-differencing the displayed CDF grid; "
        "it is not separately fitted or smoothed. No tail extrapolation is performed."
    )
    if boundary:
        notes.append(boundary.replace("> ", "").replace("**", ""))
    notes = list(dict.fromkeys(notes))
    items = "".join(f"<li>{html.escape(note)}</li>" for note in notes)
    return (
        '<div class="distribution-warnings" style="font-size:0.875em;line-height:1.5">'
        '<small style="font-size:inherit"><strong>Warnings and interpretation limits</strong><ul>'
        + items
        + "</ul></small></div>"
    )


def distribution_report(bundle, *, boundary=""):
    """Compact downloadable report with a collapsed evidence appendix and final warnings."""
    lines = [
        "# Agentic TabCF report",
        "",
        "![Estimated outcome distributions and summaries](interventional_summary.png)",
        "",
        distribution_markdown(bundle.distribution, bundle.queries),
        "",
        "<details>",
        "<summary>Technical appendix and evidence index</summary>",
        "",
        f"- Run ID: `{bundle.run_id}`",
        f"- Result bundle: `{bundle.result_bundle_id}`",
        f"- Specification: `{bundle.specification_id}`",
        f"- Dataset hash: `{bundle.dataset_hash}`",
        f"- Evidence status: `{bundle.evidence_status.value}`",
        "",
        "Diagnostic values and support assessments are retained in result_bundle.json.",
        "",
        "| Reference | Query | Validated value | Evidence ID |",
        "|---|---|---|---|",
    ]
    for index, query in enumerate(bundle.queries, 1):
        lines.append(
            f"| [{index}] | `{query.query_id}` | {query.value_display} {query.units} "
            f"| `{query.evidence_id}` |"
        )
    lines += ["", "### Warning codes", ""]
    lines.extend(f"- `{warning.code}`" for warning in bundle.warnings)
    lines += ["", "</details>", "", distribution_warning_html(bundle, boundary=boundary), ""]
    return "\n".join(lines)


def render_distribution_plot(bundle, ledger, output_path: Path):
    validate_bundle_evidence(bundle, ledger)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = bundle.distribution
    r = d["request"]
    lookup = {q.query_id: q.value_raw for q in bundle.queries}
    colors = ("#2563eb", "#f97316")
    fig, axes = plt.subplot_mosaic([["cdf", "pdf"]], figsize=(12, 4.6))
    for index, curve in enumerate(d["curves"]):
        axes["cdf"].plot(
            d["outcome_axis"],
            [lookup[k] for k in curve["cdf"]],
            color=colors[index],
            label=f"Price = {curve['price']:g}",
        )
    if r["threshold"] is not None:
        axes["cdf"].axvline(r["threshold"], color="gray", linestyle="--")
        for index, (cdf_key, probability_key) in enumerate(
            zip(d["threshold_cdf"], d["probabilities"], strict=True)
        ):
            cdf_value = lookup[cdf_key]
            axes["cdf"].scatter([r["threshold"]], [cdf_value], color=colors[index], s=28, zorder=3)
            axes["cdf"].annotate(
                f"P(> threshold) = {lookup[probability_key]:.1f}%",
                (r["threshold"], cdf_value),
                xytext=(7, 10 if index else -14),
                textcoords="offset points",
                fontsize=8,
                color=colors[index],
            )
        axes["cdf"].annotate(
            f"Outcome threshold = {r['threshold']:g}",
            (r["threshold"], 0.99),
            xytext=(6, -4),
            textcoords="offset points",
            va="top",
            fontsize=8,
            color="dimgray",
        )
    axes["cdf"].set(
        xlabel=r["outcome_units"],
        ylabel="P(sales ≤ outcome under intervention)",
        title="Interventional CDFs",
        ylim=(0, 1),
        xlim=(d["outcome_axis"][0], d["outcome_axis"][-1]),
    )
    axes["cdf"].legend(fontsize=8)

    for index, density in enumerate(d["densities"]):
        axes["pdf"].plot(
            d["density_axis"],
            [lookup[k] for k in density["pdf"]],
            color=colors[index],
            label=f"Price = {density['price']:g}",
        )
    axes["pdf"].set(
        xlabel=r["outcome_units"],
        ylabel="Approximate probability density",
        title="CDF-derived approximate density (PDF)",
        xlim=(d["outcome_axis"][0], d["outcome_axis"][-1]),
    )
    axes["pdf"].legend(fontsize=8)

    for ax in axes.values():
        ax.grid(alpha=0.2)
    fig.suptitle("Exploratory distribution estimates · Track T")
    fig.text(
        0.5,
        0.025,
        "PDF = finite-difference slope of the displayed CDF. Point estimates only; no uncertainty "
        "intervals, smoothing or tail extrapolation.",
        ha="center",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.09, 1, 0.94))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, facecolor="white")
    plt.close(fig)
