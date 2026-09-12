"""Rolling-window CAGR and benchmark-consistency calculations.

Definition: a rolling N-year return answers "if an investor had bought on
any given day and held for N years, what annualized return would they have
earned?" — computed for every possible start date the NAV history allows,
producing a distribution rather than a single number.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.returns import cagr


def rolling_returns(nav: pd.Series, window_years: float, step_days: int = 1) -> pd.Series:
    """Rolling CAGR series.

    Formula: for each start date t with an end date t + window_years in the
    series, CAGR(nav[t], nav[t + window], window_years).

    Input: a NAV series indexed by date (assumed sorted, deduplicated —
    callers are responsible for passing already-validated NAV history).

    Methodology: window length is measured in calendar days
    (round(window_years * 365.25)) and matched to the nearest available NAV
    date using `asof` semantics (the last NAV on or before the target date),
    since fund NAV isn't published on non-business days.

    `step_days` controls how densely start dates are sampled (1 = every
    available NAV date — the standard, if computationally heavier, choice).

    Limitations: returns an empty series if the history is shorter than the
    requested window — this is not an error, it means "not enough history
    for this window yet," and callers/UI must display that explicitly
    rather than a misleading empty chart.
    """
    nav = nav.sort_index()
    if nav.empty:
        return pd.Series(dtype=float)

    window_days = round(window_years * 365.25)
    dates = nav.index.to_numpy()
    results: dict = {}

    for i in range(0, len(dates), step_days):
        start_date = dates[i]
        target_end = pd.Timestamp(start_date) + pd.Timedelta(days=window_days)
        if target_end > dates[-1]:
            break
        end_pos = nav.index.searchsorted(target_end, side="right") - 1
        if end_pos <= i:
            continue
        end_date = dates[end_pos]
        nav_start, nav_end = nav.iloc[i], nav.iloc[end_pos]
        actual_years = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days / 365.25
        if actual_years <= 0:
            continue
        results[pd.Timestamp(start_date)] = cagr(nav_start, nav_end, actual_years)

    return pd.Series(results, dtype=float).sort_index()


def rolling_return_distribution(rolling: pd.Series) -> dict:
    """Summary statistics for a rolling-return series.

    Returns min, max, median and the 10th/25th/75th/90th percentiles. All
    computed with numpy's linear-interpolation percentile method (the
    standard default) — documented here because percentile methodology
    varies by library and affects the reported figures at the margins.
    """
    if rolling.empty:
        return {
            "count": 0, "min": None, "p10": None, "p25": None,
            "median": None, "p75": None, "p90": None, "max": None,
        }
    values = rolling.to_numpy()
    return {
        "count": int(len(values)),
        "min": float(np.min(values)),
        "p10": float(np.percentile(values, 10)),
        "p25": float(np.percentile(values, 25)),
        "median": float(np.median(values)),
        "p75": float(np.percentile(values, 75)),
        "p90": float(np.percentile(values, 90)),
        "max": float(np.max(values)),
    }


def benchmark_consistency(fund_rolling: pd.Series, benchmark_rolling: pd.Series) -> dict:
    """How often, and by how much, the fund beat its benchmark over the same
    rolling windows.

    Methodology: aligns the two series on their common start dates (a
    rolling return is only comparable to the benchmark's rolling return for
    the *same* window), then computes:
      - beat_rate_pct: % of aligned windows where fund CAGR > benchmark CAGR
      - avg_excess_return: mean(fund - benchmark) across aligned windows
      - median_excess_return: median(fund - benchmark)
      - worst_relative_return: min(fund - benchmark) — the single worst
        relative-performance window in the available history

    Limitations: if the two series share no common start dates (e.g. very
    short overlapping history), all fields come back None rather than a
    misleading 0%/0.0.
    """
    aligned = pd.concat(
        [fund_rolling.rename("fund"), benchmark_rolling.rename("benchmark")], axis=1
    ).dropna()
    if aligned.empty:
        return {
            "aligned_windows": 0, "beat_rate_pct": None,
            "avg_excess_return": None, "median_excess_return": None,
            "worst_relative_return": None,
        }
    excess = aligned["fund"] - aligned["benchmark"]
    return {
        "aligned_windows": int(len(aligned)),
        "beat_rate_pct": float((excess > 0).mean() * 100),
        "avg_excess_return": float(excess.mean()),
        "median_excess_return": float(excess.median()),
        "worst_relative_return": float(excess.min()),
    }
