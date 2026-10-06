"""Visitor-safe projections derived from validated TabCF result contracts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir

import numpy as np

from dcfa.constants import SupportStatus
from dcfa.errors import ErrorCode
from dcfa.evidence import EvidenceLedger, validate_bundle_evidence
from dcfa.schemas import QueryResult, ResultBundle, WarningRecord


@dataclass(frozen=True)
class PresentationMessage:
    title: str
    explanation: str
    severity: str
    action: str
    allow_numeric: bool


@dataclass(frozen=True)
class PresentedQuery:
    claim: PresentationMessage
    support: PresentationMessage
    warnings: tuple[PresentationMessage, ...]
    value_display: str | None
    units: str

    @property
    def allow_numeric(self) -> bool:
        return (
            self.value_display is not None
            and self.claim.allow_numeric
            and self.support.allow_numeric
            and all(item.allow_numeric for item in self.warnings)
        )


@dataclass(frozen=True)
class VisitorPlotProjection:
    x_grid: tuple[float, ...]
    y_grid: tuple[float, ...]
    cdf: tuple[tuple[float, ...], ...]
    means: tuple[float, ...]
    quantile_levels: tuple[float, ...]
    quantiles: tuple[tuple[float, ...], ...]
    x_label: str = "Treatment level"
    y_label: str = "Outcome value"
    cdf_label: str = "Cumulative probability"


CLAIM_PRESENTATION: dict[str, PresentationMessage] = {
    "interventional_mean": PresentationMessage(
        "Estimated mean outcome",
        "The estimated average outcome at the requested treatment level.",
        "info",
        "Interpret this together with the data-support status and limitations.",
        True,
    ),
    "interventional_quantile": PresentationMessage(
        "Estimated outcome quantile",
        "The estimated outcome quantile at the requested treatment level.",
        "info",
        "Interpret this together with the data-support status and limitations.",
        True,
    ),
    "threshold_risk": PresentationMessage(
        "Estimated threshold probability",
        "The estimated probability of crossing the requested outcome threshold.",
        "info",
        "Interpret this together with the data-support status and limitations.",
        True,
    ),
    "mean_contrast_x_minus_comparison_x": PresentationMessage(
        "Estimated mean outcome difference",
        "The estimated difference in mean outcome between the requested treatment levels.",
        "info",
        "Interpret the direction in the order stated in the submitted question.",
        True,
    ),
    "quantile_contrast_x_minus_comparison_x": PresentationMessage(
        "Estimated outcome quantile difference",
        "The estimated difference in the requested outcome quantile between treatment levels.",
        "info",
        "Interpret the direction in the order stated in the submitted question.",
        True,
    ),
    "risk_contrast_x_minus_comparison_x": PresentationMessage(
        "Estimated threshold-probability difference",
        "The estimated difference in threshold probability between treatment levels.",
        "info",
        "Interpret the direction in the order stated in the submitted question.",
        True,
    ),
}

UNKNOWN_CLAIM = PresentationMessage(
    "Result unavailable",
    "This result type is not approved for visitor display.",
    "blocked",
    "Use the artifact verifier to inspect the run locally.",
    False,
)

SUPPORT_PRESENTATION: dict[SupportStatus, PresentationMessage] = {
    SupportStatus.SUPPORTED: PresentationMessage(
        "Supported by the observed data",
        "The requested treatment levels passed the demo's empirical support checks.",
        "info",
        "Keep the identification assumptions and development-only boundary in view.",
        True,
    ),
    SupportStatus.WEAK_SUPPORT: PresentationMessage(
        "Limited data support",
        "At least one requested treatment level has weak empirical support.",
        "caution",
        "Treat the estimate cautiously and consider a better-supported treatment range.",
        True,
    ),
    SupportStatus.UNSUPPORTED: PresentationMessage(
        "Outside observed data support",
        "The requested treatment level is not supported by the observed data.",
        "blocked",
        "Choose treatment levels within the supported range.",
        False,
    ),
}

UNKNOWN_SUPPORT = PresentationMessage(
    "Data support could not be verified",
    "The support status is not approved for visitor display.",
    "blocked",
    "Inspect the run with the local artifact verifier.",
    False,
)

WARNING_PRESENTATION: dict[str, PresentationMessage] = {
    "DEVELOPMENT_TABPFN_NOT_RELEASE_ELIGIBLE": PresentationMessage(
        "Development result",
        "This TabPFN result uses a recorded development-only backend profile and is not "
        "release-ready evidence.",
        "info",
        "Do not use it as a published or production causal claim.",
        True,
    ),
    "DEVELOPMENT_FALLBACK_NOT_TABCF": PresentationMessage(
        "Unapproved analysis backend",
        "The result did not use the managed TabPFN path required by this demo.",
        "blocked",
        "Inspect the local artifact and backend configuration.",
        False,
    ),
    "WEAK_FIRST_STAGE_EMPIRICAL_WARNING": PresentationMessage(
        "Weak instrument signal",
        "The empirical first-stage signal is below the demo's development threshold.",
        "caution",
        "Treat the estimate cautiously; this diagnostic does not prove validity or invalidity.",
        True,
    ),
    "CONTROL_RANK_CALIBRATION_WARNING": PresentationMessage(
        "Control-rank calibration concern",
        "The estimated control rank departs from its development reference.",
        "caution",
        "Review the diagnostic artifact before relying on the estimate.",
        True,
    ),
    "RESIDUAL_DEPENDENCE_EMPIRICAL_WARNING": PresentationMessage(
        "Residual dependence remains",
        "An empirical residual-dependence diagnostic remains elevated.",
        "caution",
        "Treat the estimate cautiously; this check does not establish instrument validity.",
        True,
    ),
    "WEAK_INTERVENTION_SUPPORT": PresentationMessage(
        "Some treatment levels have limited support",
        "At least one analyzed treatment level has weak empirical joint support.",
        "caution",
        "Prefer treatment levels with stronger observed-data support.",
        True,
    ),
}

UNKNOWN_WARNING = PresentationMessage(
    "Additional review required",
    "The run contains a warning that is not approved for visitor display.",
    "blocked",
    "Inspect the local artifact before presenting a numerical result.",
    False,
)

ERROR_PRESENTATION: dict[str, PresentationMessage] = {
    "input": PresentationMessage(
        "Input needs attention",
        "The request does not meet the demo's bounded input requirements.",
        "blocked",
        "Check the selected roles, values, file shape, and confirmation, then try again.",
        False,
    ),
    "support": PresentationMessage(
        "Outside observed data support",
        "The requested treatment level is not supported by the observed data.",
        "blocked",
        "Choose treatment levels within the supported range.",
        False,
    ),
    "service": PresentationMessage(
        "Analysis service is temporarily unavailable",
        "A required external analysis service did not complete the request.",
        "blocked",
        "Try again later or ask the local operator to check service readiness.",
        False,
    ),
    "verification": PresentationMessage(
        "Result verification failed",
        "The run could not be matched to a valid, evidence-linked result.",
        "blocked",
        "Do not use a numerical result; inspect the run with the local verifier.",
        False,
    ),
}

ERROR_CATEGORY_BY_CODE: dict[ErrorCode, str] = {
    ErrorCode.INVALID_SPECIFICATION: "input",
    ErrorCode.MISSING_CAUSAL_ROLE: "input",
    ErrorCode.ROLE_CONFLICT: "input",
    ErrorCode.UNSUPPORTED_BASELINE_COVARIATES: "input",
    ErrorCode.UNSUPPORTED_TREATMENT: "input",
    ErrorCode.UNSUPPORTED_BACKEND_PROFILE: "service",
    ErrorCode.INVALID_DATA: "input",
    ErrorCode.OUTSIDE_SUPPORT: "support",
    ErrorCode.BACKEND_IMPORT_FAILED: "service",
    ErrorCode.BACKEND_LOAD_FAILED: "service",
    ErrorCode.BACKEND_FIT_FAILED: "service",
    ErrorCode.BACKEND_PREDICT_FAILED: "service",
    ErrorCode.MANAGED_QUOTA_EXHAUSTED: "service",
    ErrorCode.MANAGED_RATE_LIMITED: "service",
    ErrorCode.MANAGED_SERVICE_FAILED: "service",
    ErrorCode.V2_UNAVAILABLE: "service",
    ErrorCode.V2_EXECUTION_FAILED: "service",
    ErrorCode.LLM_IMPORT_FAILED: "service",
    ErrorCode.LLM_API_FAILED: "service",
    ErrorCode.LLM_OUTPUT_INVALID: "service",
    ErrorCode.EVIDENCE_NOT_FOUND: "verification",
    ErrorCode.EVIDENCE_MISMATCH: "verification",
    ErrorCode.HASH_MISMATCH: "verification",
    ErrorCode.STALE_ID: "verification",
    ErrorCode.RELEASE_GATE_FAILED: "verification",
    ErrorCode.CACHE_MISMATCH: "verification",
    ErrorCode.DATA_ACCESS_BLOCKED: "input",
    ErrorCode.SPLIT_LEAKAGE: "verification",
    ErrorCode.POLICY_NOT_FROZEN: "verification",
    ErrorCode.CONSTRAINT_VIOLATION: "input",
    ErrorCode.OUTPUT_PATH_EXISTS: "input",
}

_INTERNAL_UNIT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*_units$")
_SAFE_UNIT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9 ./%°-]{0,39}$")


def display_value(value: float) -> str:
    """Apply visitor precision without changing the evidence-bound raw value."""
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("A visitor display value must be finite.")
    return format(numeric, ".3g")


def quantile_label(level: float) -> str:
    """Return an approved visitor label for a validated quantile level."""
    numeric = float(level)
    return "Median" if math.isclose(numeric, 0.5) else f"{numeric:.0%} quantile"


def present_units(units: str) -> str:
    """Translate internal role-derived units and reject unsafe free-form labels."""
    normalized = str(units).strip()
    if normalized == "outcome_units" or _INTERNAL_UNIT_PATTERN.fullmatch(normalized):
        return "outcome units"
    if _SAFE_UNIT_PATTERN.fullmatch(normalized):
        return normalized
    return "outcome units"


def present_warning(warning: WarningRecord) -> PresentationMessage:
    if warning.code in {
        "DISTRIBUTIONAL_POINT_ESTIMATES",
        "POOLED_STATE_YEAR_LIMITATIONS",
        "QUANTILE_GRID_ENDPOINT",
    }:
        return PresentationMessage(
            "Distribution scope",
            warning.message,
            "warning",
            "Restrict conclusions to the evaluated distribution.",
            True,
        )
    return WARNING_PRESENTATION.get(warning.code, UNKNOWN_WARNING)


def present_error(code: str | ErrorCode | None) -> PresentationMessage:
    try:
        error_code = code if isinstance(code, ErrorCode) else ErrorCode(str(code))
    except ValueError:
        return ERROR_PRESENTATION["verification"]
    return ERROR_PRESENTATION[ERROR_CATEGORY_BY_CODE[error_code]]


def present_query(query: QueryResult) -> PresentedQuery:
    claim = CLAIM_PRESENTATION.get(query.claim_type, UNKNOWN_CLAIM)
    if re.fullmatch(
        r"distribution:(quantile:(0\.25|0\.5|0\.75|0\.9):[01]|"
        r"quantile_difference:(0\.25|0\.5|0\.75|0\.9)|exceedance:[01]|"
        r"exceedance_difference|upper_minus_middle_change|threshold_cdf:[01]|"
        r"cdf:[01]:[0-9]+|density:[01]:[0-9]+)",
        query.claim_type,
    ):
        claim = PresentationMessage(
            "Original-unit distribution",
            "Evidence-linked point estimate.",
            "warning",
            "Retain all interpretation warnings.",
            True,
        )
    support = SUPPORT_PRESENTATION.get(query.support_status, UNKNOWN_SUPPORT)
    warnings = tuple(present_warning(item) for item in query.warnings)
    allowed = (
        claim.allow_numeric
        and support.allow_numeric
        and all(item.allow_numeric for item in warnings)
    )
    return PresentedQuery(
        claim=claim,
        support=support,
        warnings=warnings,
        value_display=display_value(query.value_raw) if allowed else None,
        units=present_units(query.units),
    )


_WEBSITE_OBJECTIVE_BY_CLAIM = {
    "interventional_mean": "mean",
    "interventional_quantile": "quantile",
    "mean_contrast_x_minus_comparison_x": "mean_contrast",
    "quantile_contrast_x_minus_comparison_x": "quantile_contrast",
}
_TREATMENT_LABELS = {"low": "low", "center": "center", "high": "high"}


def answer_sentence(query: QueryResult, proposal: object) -> str:
    """Answer directly when an approved symbolic compilation matches the query."""
    presented = present_query(query)
    if not presented.allow_numeric:
        return "No numerical answer is approved for visitor display."
    fallback = (
        f"{presented.claim.explanation} The estimate is "
        f"{presented.value_display} {presented.units}."
    )
    if not isinstance(proposal, dict):
        return fallback
    objective = proposal.get("objective")
    if objective != _WEBSITE_OBJECTIVE_BY_CLAIM.get(query.claim_type):
        return fallback
    x_label = _TREATMENT_LABELS.get(proposal.get("x_label"))
    if x_label is None:
        return fallback
    summary = "mean" if objective.startswith("mean") else "median"
    if objective.endswith("_contrast"):
        comparison_label = _TREATMENT_LABELS.get(proposal.get("comparison_x_label"))
        if comparison_label is None or comparison_label == x_label:
            return fallback
        magnitude = display_value(abs(query.value_raw))
        if math.isclose(float(query.value_raw), 0.0, abs_tol=1e-12):
            return (
                f"From the {comparison_label} to the {x_label} treatment level, "
                f"the estimated {summary} outcome does not change."
            )
        direction = "increases" if query.value_raw > 0 else "decreases"
        return (
            f"From the {comparison_label} to the {x_label} treatment level, "
            f"the estimated {summary} outcome {direction} by {magnitude} "
            f"{presented.units}."
        )
    return (
        f"At the {x_label} treatment level, the estimated {summary} outcome is "
        f"{presented.value_display} {presented.units}."
    )


def build_visitor_plot_projection(
    bundle: ResultBundle,
    ledger: EvidenceLedger,
) -> VisitorPlotProjection:
    """Validate the bundle before projecting its arrays into visitor plot data."""
    validate_bundle_evidence(bundle, ledger)
    return VisitorPlotProjection(
        x_grid=tuple(float(value) for value in bundle.x_grid),
        y_grid=tuple(float(value) for value in bundle.y_grid),
        cdf=tuple(tuple(float(value) for value in row) for row in bundle.interventional_cdf),
        means=tuple(float(value) for value in bundle.interventional_mean),
        quantile_levels=tuple(float(value) for value in bundle.quantile_levels),
        quantiles=tuple(
            tuple(float(value) for value in row) for row in bundle.interventional_quantiles
        ),
    )


def render_visitor_plot(
    bundle: ResultBundle,
    ledger: EvidenceLedger,
    output_path: Path,
) -> VisitorPlotProjection:
    """Render a visitor plot while leaving the identity-rich audit plot untouched."""
    projection = build_visitor_plot_projection(bundle, ledger)

    import os

    matplotlib_config = Path(gettempdir()) / "dcfa-matplotlib-cache"
    matplotlib_config.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_config))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x_grid = np.asarray(projection.x_grid, dtype=float)
    y_grid = np.asarray(projection.y_grid, dtype=float)
    cdf = np.asarray(projection.cdf, dtype=float)
    means = np.asarray(projection.means, dtype=float)
    quantiles = np.asarray(projection.quantiles, dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    selected_indices = np.linspace(0, len(x_grid) - 1, min(4, len(x_grid))).round().astype(int)
    for index in selected_indices:
        axes[0].plot(y_grid, cdf[index], label=f"Treatment {x_grid[index]:.3g}")
    axes[0].set_title("Estimated outcome distributions")
    axes[0].set_xlabel(projection.y_label)
    axes[0].set_ylabel(projection.cdf_label)
    axes[0].set_ylim(-0.02, 1.02)
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.25)

    axes[1].plot(x_grid, means, marker="o", label="Mean")
    for level_index, level in enumerate(projection.quantile_levels):
        axes[1].plot(x_grid, quantiles[:, level_index], label=quantile_label(level))
    axes[1].set_title("Outcome summaries by treatment level")
    axes[1].set_xlabel(projection.x_label)
    axes[1].set_ylabel(projection.y_label)
    axes[1].legend(frameon=False)
    axes[1].grid(alpha=0.25)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, facecolor="white")
    plt.close(fig)
    return projection
