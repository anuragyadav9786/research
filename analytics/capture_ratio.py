"""Upside and downside capture ratios versus a benchmark."""
from __future__ import annotations

import pandas as pd


def _geometric_compound(returns: pd.Series) -> float:
    """Cumulative compounded return of a return series: prod(1+r) - 1."""
    return float((1.0 + returns).prod() - 1.0)


def _capture_ratio(fund_returns: pd.Series, benchmark_returns: pd.Series, upside: bool) -> float | None:
    aligned = pd.concat(
        [fund_returns.rename("fund"), benchmark_returns.rename("benchmark")], axis=1
    ).dropna()
    mask = aligned["benchmark"] > 0 if upside else aligned["benchmark"] < 0
    subset = aligned.loc[mask]
    if subset.empty:
        return None
    fund_compound = _geometric_compound(subset["fund"])
    benchmark_compound = _geometric_compound(subset["benchmark"])
    if benchmark_compound == 0:
        return None
    return (fund_compound / benchmark_compound) * 100.0


def upside_capture(fund_returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    """Upside Capture Ratio.

    Definition: how much of the benchmark's gain the fund captured during
    periods when the benchmark was positive.

    Formula: [compound(fund returns during benchmark-positive periods) /
              compound(benchmark returns during those same periods)] * 100

    Interpretation: 100 = matched the benchmark's upside exactly; >100 =
    outperformed during rallies; <100 = lagged during rallies.

    Limitations: returns None (not 0 or an error) if the benchmark had no
    positive periods in the sample — this happens with very short windows
    and must be surfaced as "insufficient data," not a fabricated ratio.
    """
    return _capture_ratio(fund_returns, benchmark_returns, upside=True)


def downside_capture(fund_returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    """Downside Capture Ratio.

    Definition: how much of the benchmark's decline the fund also
    experienced during periods when the benchmark was negative.

    Formula: [compound(fund returns during benchmark-negative periods) /
              compound(benchmark returns during those same periods)] * 100

    Interpretation: 100 = fell exactly as much as the benchmark; <100 =
    better downside resilience (fell less); >100 = fell more than the
    benchmark during its declines (worse downside behaviour).

    Limitations: same "no negative benchmark periods -> None" behaviour as
    `upside_capture`.
    """
    return _capture_ratio(fund_returns, benchmark_returns, upside=False)
