"""Validate row-free exact-unit proposals against explicit user instructions."""

from __future__ import annotations

import re

from dcfa.schemas import DistributionRequest
from dcfa.tabcf_iv.distribution import validate_distribution_request
from dcfa_website_demo.gemini import _parse_proposal, _validate_proposal

_PAIR = re.compile(
    r"(?:from|从)\s*(\d+(?:\.\d+)?)[^\d\n]{0,60}?(?:to|到|提高到|增加到)\s*(\d+(?:\.\d+)?)", re.I
)


def numeric_proposal(proposal, history, columns, overrides):
    """Reuse role/scope checks; numerical values are never computed by the LLM."""
    import json

    text = "\n".join(e["content"] for e in history if e["role"] == "user")
    pairs = _PAIR.findall(text)
    raw = proposal.get("distribution") if isinstance(proposal, dict) else None
    if raw is None:
        if pairs:
            raise ValueError("Exact numeric interventions cannot be replaced by symbolic labels.")
        parsed = _parse_proposal(json.dumps(proposal))
        return (
            parsed,
            _validate_proposal(parsed, columns=columns, role_overrides=overrides, csv_mode=True),
            None,
        )
    expected = {
        "prices",
        "threshold",
        "treatment_units",
        "outcome_units",
        "treatment_scale",
        "outcome_scale",
        "scale_quote",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("Invalid numeric request fields.")
    d = DistributionRequest(
        **{k: tuple(v) if k == "prices" else v for k, v in raw.items() if k != "scale_quote"}
    )
    validate_distribution_request(d)
    quote = raw["scale_quote"]
    if (
        not isinstance(quote, str)
        or quote not in text
        or not re.search(r"already.*natural.log|已经.*自然对数|已.*自然对数", quote, re.I)
    ):
        raise ValueError("Explicit already-natural-log CSV declaration is required.")
    both_scales_explicit = (
        len(re.findall(r"natural.log|自然对数", quote, re.I)) >= 2
        or (re.search(r"\bX\b", quote) and re.search(r"\bY\b", quote))
        or ("treatment" in quote.lower() and "outcome" in quote.lower())
    )
    if not both_scales_explicit:
        raise ValueError("The already-log declaration must explicitly cover both X and Y.")
    if not pairs or tuple(map(float, pairs[-1])) != d.prices:
        raise ValueError("Interventions must preserve the user's exact from/to values.")
    for unit in (d.treatment_units, d.outcome_units):
        if unit not in text:
            raise ValueError("Original-unit labels must quote the user.")
    if d.threshold is not None:
        threshold_pattern = rf"(?:exceeding|exceeds|above|超过)\s*{d.threshold:g}(?![\d.])"
        if not re.search(threshold_pattern, text, re.I):
            raise ValueError("The original-unit exceedance threshold must be explicit.")
    elif re.search(r"(?:exceeding|exceeds|above|超过)\s*\d", text, re.I):
        raise ValueError("An explicit exceedance request cannot be silently omitted.")
    if (
        proposal.get("objective") != "distribution"
        or proposal.get("x_label") != "exact"
        or proposal.get("comparison_x_label") != "exact"
        or proposal.get("level_label") != "quartiles"
    ):
        raise ValueError("Numeric distribution requests cannot use symbolic interventions.")
    parsed = _parse_proposal(json.dumps({k: v for k, v in proposal.items() if k != "distribution"}))
    values = _validate_proposal(
        parsed, columns=columns, role_overrides=overrides, csv_mode=True, allow_distribution=True
    )
    return proposal, values, d
