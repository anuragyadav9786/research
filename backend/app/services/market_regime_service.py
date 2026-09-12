"""Bridges the per-regime analytics (analytics/market_regime.py) to the
Phase 10 API response — deterministic templated summaries only, built
directly from computed numbers (never an LLM call), per Rule 4.
"""
from __future__ import annotations

import pandas as pd

from analytics.market_regime import regime_metrics
from app.models.reference import MarketRegime


def _summary(fund: dict, benchmark: dict | None) -> str:
    if not fund["available"]:
        return "Not enough NAV history to evaluate this fund during this period."

    fund_return = fund["return_pct"]
    if benchmark is None or not benchmark["available"]:
        return f"Returned {fund_return:+.1f}% during this period (no benchmark comparison available)."

    excess = fund_return - benchmark["return_pct"]
    if excess > 0.05:
        return (
            f"Outperformed its benchmark by {excess:.1f} percentage points during this period "
            f"({fund_return:+.1f}% vs {benchmark['return_pct']:+.1f}%)."
        )
    if excess < -0.05:
        return (
            f"Underperformed its benchmark by {abs(excess):.1f} percentage points during this period "
            f"({fund_return:+.1f}% vs {benchmark['return_pct']:+.1f}%)."
        )
    return f"Matched its benchmark during this period ({fund_return:+.1f}%)."


def compute_regime_behavior(
    nav: pd.Series, benchmark: pd.Series | None, regimes: list[MarketRegime]
) -> dict:
    results = []
    outperform_count = 0
    comparable_count = 0

    for regime in regimes:
        end = regime.end_date if regime.end_date is not None else nav.index.max()
        fund_result = regime_metrics(nav, regime.start_date, end)
        benchmark_result = regime_metrics(benchmark, regime.start_date, end) if benchmark is not None else None

        excess = None
        outperformed = None
        if fund_result["available"] and benchmark_result is not None and benchmark_result["available"]:
            excess = round(fund_result["return_pct"] - benchmark_result["return_pct"], 4)
            outperformed = excess > 0
            comparable_count += 1
            if outperformed:
                outperform_count += 1

        results.append({
            "regime_name": regime.name,
            "regime_type": regime.regime_type,
            "start_date": regime.start_date,
            "end_date": regime.end_date,
            "fund_available": fund_result["available"],
            "fund_return_pct": round(fund_result["return_pct"], 4) if fund_result["available"] else None,
            "fund_volatility_pct": (
                round(fund_result["volatility_pct"], 4) if fund_result["volatility_pct"] is not None else None
            ),
            "fund_max_drawdown_pct": (
                round(fund_result["max_drawdown_pct"], 4) if fund_result["available"] else None
            ),
            "benchmark_available": benchmark_result["available"] if benchmark_result else False,
            "benchmark_return_pct": (
                round(benchmark_result["return_pct"], 4)
                if benchmark_result and benchmark_result["available"] else None
            ),
            "excess_return_pct": excess,
            "outperformed": outperformed,
            "summary": _summary(fund_result, benchmark_result),
        })

    return {
        "regimes": results,
        "regimes_with_comparison": comparable_count,
        "regimes_outperformed": outperform_count,
    }
