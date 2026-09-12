"""Portfolio concentration calculations (Section 9: Concentration & Hidden
Risk Engine — the single-fund-visible-concentration half of it; the
cross-fund "hidden concentration" half needs the Overlap Engine, Phase 8).

All functions take plain (label, weight_pct) pairs so they work uniformly
for top-holdings, sector concentration, and market-cap concentration —
there is nothing holdings-specific about "sum of squared shares."
"""
from __future__ import annotations


def group_weights(items: list[tuple[str, float]]) -> dict[str, float]:
    """Aggregate weight_pct by label — the shared primitive behind sector
    allocation, market-cap allocation, or any other "% of portfolio by
    category" breakdown. Formula: sum of weights sharing the same label."""
    totals: dict[str, float] = {}
    for label, weight_pct in items:
        totals[label] = totals.get(label, 0.0) + weight_pct
    return totals


def top_n_weight_pct(weights_pct: list[float], n: int) -> float:
    """Sum of the largest n weights (e.g. "top 5 holdings make up X% of
    the portfolio"). Formula: sum(sorted(weights, descending)[:n]).

    If the portfolio has fewer than n holdings, sums all of them — this is
    not an error, a concentrated small portfolio can legitimately have
    fewer than 10 holdings.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    return sum(sorted(weights_pct, reverse=True)[:n])


def herfindahl_hirschman_index(weights_pct: list[float]) -> float:
    """Herfindahl-Hirschman Index of portfolio concentration.

    Formula: HHI = sum((weight_pct_i / 100)^2) * 10000

    This is the standard HHI scale (0-10000), the same one used in
    antitrust market-concentration analysis (US DOJ/FTC Horizontal Merger
    Guidelines), adapted here to portfolio weights instead of market
    shares — a fund holding N equally-weighted positions has
    HHI = 10000/N (e.g. 20 equal-weight holdings -> HHI = 500).

    Interpretation (the DOJ/FTC thresholds, commonly reused for portfolio
    concentration by extension — see `hhi_label`):
      - HHI < 1500: diversified
      - 1500 <= HHI < 2500: moderate concentration
      - HHI >= 2500: high concentration

    Limitations: HHI only sees the holdings passed in — if the portfolio
    weights sum to well under 100% (e.g. only top-10 disclosed, not full
    holdings), HHI understates true concentration. Always report alongside
    the total disclosed weight so this limitation is visible.
    """
    return sum((w / 100.0) ** 2 for w in weights_pct) * 10000


def hhi_label(hhi: float) -> str:
    """Qualitative label for an HHI score, using the DOJ/FTC convention
    documented in `herfindahl_hirschman_index`. A label, not a verdict —
    see that function's docstring for why these thresholds, specifically."""
    if hhi < 1500:
        return "diversified"
    if hhi < 2500:
        return "moderate_concentration"
    return "high_concentration"
