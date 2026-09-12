"""Pairwise fund overlap calculations (Section 11: Fund Overlap Engine).

Everything here is generic over "a dict of label -> weight_pct" — the same
`weighted_overlap_pct` formula computes security overlap (labels are
security names), sector overlap (labels are sector names), or any other
weight-by-category overlap without duplicating the math.
"""
from __future__ import annotations


def weighted_overlap_pct(weights_a: dict[str, float], weights_b: dict[str, float]) -> float:
    """Weight-adjusted overlap between two portfolios.

    Formula: sum(min(weight_a.get(label, 0), weight_b.get(label, 0))
                  for label in union(weights_a.keys(), weights_b.keys()))

    This is the standard "portfolio overlap" methodology used by fund
    research tools: for each holding, only the *smaller* of the two
    weights counts, because that's the portion of exposure genuinely
    shared by both portfolios. A label held only by one fund contributes
    zero.

    Interpretation: 0% = no shared exposure at all; 100% = identical
    portfolios (by weight). There is no official regulatory threshold for
    "how much overlap is too much" (unlike HHI's DOJ/FTC convention) — see
    `overlap_label` for the practitioner heuristic used here, documented
    as exactly that: a heuristic, not a standard.

    Limitations: says nothing about *why* two funds overlap (shared
    factor exposure vs. coincidence) or about overlap with funds not in
    the comparison — see the Portfolio-level analysis in a later phase for
    that.
    """
    labels = set(weights_a) | set(weights_b)
    return sum(min(weights_a.get(label, 0.0), weights_b.get(label, 0.0)) for label in labels)


def overlap_counts(weights_a: dict[str, float], weights_b: dict[str, float]) -> dict:
    """How many labels are shared vs. exclusive to each side.

    Formula: set intersection/difference sizes — a structural count,
    independent of weight (a tiny 0.1% holding counts the same as a 9%
    one here; `weighted_overlap_pct` is where weight matters).
    """
    keys_a, keys_b = set(weights_a), set(weights_b)
    return {
        "common": len(keys_a & keys_b),
        "only_in_a": len(keys_a - keys_b),
        "only_in_b": len(keys_b - keys_a),
    }


def overlap_label(weighted_overlap_pct_value: float) -> str:
    """Qualitative label for a weighted-overlap score.

    Thresholds (< 20% low, 20-50% moderate, >= 50% high) are a commonly
    cited practitioner rule of thumb in fund-overlap commentary — UNLIKE
    HHI's DOJ/FTC thresholds, there is no official regulatory standard for
    portfolio overlap. This is documented uncertainty (per the project's
    "don't guess, document the uncertainty" rule for financial
    methodology), not a precise scientific cutoff. Treat the label as a
    starting point for review, not a verdict.
    """
    if weighted_overlap_pct_value < 20:
        return "low_overlap"
    if weighted_overlap_pct_value < 50:
        return "moderate_overlap"
    return "high_overlap"
