"""Bridges the deterministic analytics engine (analytics/, repo root) to
the API layer's response shapes.

This is the only place that decides *how* a metric is presented (rounding,
percentage conversion, "insufficient data" fallbacks) — analytics/ itself
stays pure and reusable, app/api/funds.py stays a thin HTTP layer.

Every function here returns plain dicts shaped to match the corresponding
Pydantic schema in app/schemas/funds.py, and never raises for "not enough
data" — that's reported as an explicit `available: False` / reason field,
consistent with how the analytics functions themselves prefer None over a
fabricated number.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from analytics.alpha_beta import annualize_return
from analytics.alpha_beta import beta as compute_beta
from analytics.alpha_beta import jensen_alpha
from analytics.capture_ratio import downside_capture, upside_capture
from analytics.drawdown import max_drawdown
from analytics.returns import cagr_for_window, returns_series
from analytics.risk import annualized_volatility, downside_deviation, sharpe_ratio, sortino_ratio
from analytics.rolling_returns import benchmark_consistency, rolling_return_distribution, rolling_returns

RETURN_WINDOWS_YEARS = {"1y": 1, "3y": 3, "5y": 5, "7y": 7, "10y": 10}
MIN_OBSERVATIONS_FOR_RISK = 2

# Rolling-return bar chart (see compute_rolling_return_series): two
# independent axes, matching the request in plain terms — "3-month rolling
# return, plotted over the last 1 year" — rather than one flat list of
# window choices.
ROLLING_SERIES_WINDOWS_YEARS = {"1m": 1 / 12, "3m": 0.25, "6m": 0.5, "1y": 1.0}
ROLLING_SERIES_LOOKBACK_YEARS = {"1y": 1, "3y": 3, "5y": 5, "10y": 10}
# A bar per NAV date over a 10-year lookback would be thousands of
# illegible slivers, so the shown points are downsampled — but evenly to
# a flat cap regardless of `window` made every window length look like
# the same chart at a given lookback (e.g. "1 Month" and "3 Month" over
# "1 Year" both landed near MAX_ROLLING_SERIES_POINTS, since both start
# from the same ~252 daily observations): picking a different window
# visibly changed each bar's VALUE but not the chart's shape, which read
# as the control "not doing anything." Sampling cadence is now targeted
# to roughly lookback/window bars (e.g. a 1-month window over a 1-year
# lookback aims for ~12 bars, one per month) — still genuine overlapping
# rolling returns, just shown at a cadence that scales with the chosen
# window the way the control implies, clamped to a sane range so neither
# a long window over a short lookback (too few bars to read as a chart)
# nor a short window over a long lookback (still thousands of slivers)
# breaks it.
MIN_ROLLING_SERIES_POINTS = 3
MAX_ROLLING_SERIES_POINTS = 60


def series_to_points(series: pd.Series) -> list[dict]:
    """Serialize a date-indexed NAV/benchmark series for the raw
    nav-history endpoint. No analytics — a straight data feed for charts."""
    return [{"date": _to_date(idx), "value": round(float(v), 4)} for idx, v in series.items()]


def _to_date(value) -> date | None:
    if value is None:
        return None
    return pd.Timestamp(value).date()


def compute_returns(nav: pd.Series, nav_history_backfilled: bool = False) -> dict:
    """`nav_history_backfilled` should reflect whether this variant's full
    NAV history has already been pulled from mfapi.in
    (SchemeVariant.nav_history_backfilled_at is set) — see
    lazy_nav_backfill.py. It's what lets an unavailable window be reported
    as "scheme_too_young" (we've confirmed there's no earlier NAV to find)
    rather than the more conservative "insufficient_history" (we haven't
    finished checking, so we can't yet tell the two apart). Callers that
    don't have a variant on hand (category/discovery aggregates) can omit
    it — every unavailable window then reads "insufficient_history", the
    same behaviour this function always had.

    Note "scheme_too_young" is never a fabricated legal launch date — see
    ReturnWindow.earliest_nav_date's docstring in app/schemas/funds.py."""
    if nav.empty:
        return {
            "as_of_date": None,
            "windows": {
                label: {"available": False, "cagr_pct": None, "start_date": None, "end_date": None,
                        "reason": "no_nav_history", "earliest_nav_date": None}
                for label in RETURN_WINDOWS_YEARS
            },
        }

    end_date = nav.index[-1]
    earliest_nav_date = nav.index[0]
    windows = {}
    for label, years in RETURN_WINDOWS_YEARS.items():
        target_start = end_date - pd.Timedelta(days=round(years * 365.25))
        if target_start < earliest_nav_date:
            if nav_history_backfilled:
                windows[label] = {
                    "available": False, "cagr_pct": None, "start_date": None, "end_date": None,
                    "reason": "scheme_too_young", "earliest_nav_date": _to_date(earliest_nav_date),
                }
            else:
                windows[label] = {
                    "available": False, "cagr_pct": None, "start_date": None, "end_date": None,
                    "reason": "insufficient_history", "earliest_nav_date": None,
                }
            continue
        window_nav = nav.loc[target_start:end_date]
        cagr_value = cagr_for_window(nav, target_start, end_date)
        if cagr_value is None:
            windows[label] = {
                "available": False, "cagr_pct": None, "start_date": None, "end_date": None,
                "reason": "insufficient_history", "earliest_nav_date": None,
            }
        else:
            windows[label] = {
                "available": True,
                "cagr_pct": round(cagr_value * 100, 4),
                "start_date": _to_date(window_nav.index[0]),
                "end_date": _to_date(end_date),
                "reason": None,
                "earliest_nav_date": None,
            }

    return {"as_of_date": _to_date(end_date), "windows": windows}


def compute_risk(nav: pd.Series, benchmark: pd.Series | None, risk_free_rate_annual: float) -> dict:
    fund_returns = returns_series(nav)
    if len(fund_returns) < MIN_OBSERVATIONS_FOR_RISK:
        return {
            "available": False, "reason": "insufficient_history", "observations_used": len(fund_returns),
            "risk_free_rate_pct": round(risk_free_rate_annual * 100, 4),
            "volatility_pct": None, "downside_deviation_pct": None,
            "sharpe_ratio": None, "sortino_ratio": None,
            "upside_capture_pct": None, "downside_capture_pct": None,
            "beta": None, "jensen_alpha_pct": None,
        }

    volatility = annualized_volatility(fund_returns)
    downside_dev = downside_deviation(fund_returns)

    try:
        sharpe = sharpe_ratio(fund_returns, risk_free_rate_annual)
    except ValueError:
        sharpe = None
    try:
        sortino = sortino_ratio(fund_returns, risk_free_rate_annual)
    except ValueError:
        sortino = None

    upside_cap = downside_cap = fund_beta = jensen_alpha_pct = None
    if benchmark is not None and not benchmark.empty:
        bench_returns = returns_series(benchmark)
        upside_cap = upside_capture(fund_returns, bench_returns)
        downside_cap = downside_capture(fund_returns, bench_returns)
        try:
            fund_beta = compute_beta(fund_returns, bench_returns)
            fund_ann = annualize_return(fund_returns)
            bench_ann = annualize_return(bench_returns)
            jensen_alpha_pct = round(
                jensen_alpha(fund_ann, bench_ann, risk_free_rate_annual, fund_beta) * 100, 4
            )
        except ValueError:
            fund_beta = None
            jensen_alpha_pct = None

    return {
        "available": True,
        "reason": None,
        "observations_used": len(fund_returns),
        "risk_free_rate_pct": round(risk_free_rate_annual * 100, 4),
        "volatility_pct": round(volatility * 100, 4),
        "downside_deviation_pct": round(downside_dev * 100, 4),
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "sortino_ratio": round(sortino, 4) if sortino is not None else None,
        "upside_capture_pct": round(upside_cap, 4) if upside_cap is not None else None,
        "downside_capture_pct": round(downside_cap, 4) if downside_cap is not None else None,
        "beta": round(fund_beta, 4) if fund_beta is not None else None,
        "jensen_alpha_pct": jensen_alpha_pct,
    }


def _pct(value: float | None) -> float | None:
    return round(value * 100, 4) if value is not None else None


def _distribution_to_pct(distribution: dict) -> dict:
    return {
        "count": distribution["count"],
        **{key: _pct(distribution[key]) for key in ("min", "p10", "p25", "median", "p75", "p90", "max")},
    }


def _consistency_to_pct(consistency: dict) -> dict:
    return {
        "aligned_windows": consistency["aligned_windows"],
        "beat_rate_pct": round(consistency["beat_rate_pct"], 4) if consistency["beat_rate_pct"] is not None else None,
        "avg_excess_return": _pct(consistency["avg_excess_return"]),
        "median_excess_return": _pct(consistency["median_excess_return"]),
        "worst_relative_return": _pct(consistency["worst_relative_return"]),
    }


def compute_rolling_returns(nav: pd.Series, benchmark: pd.Series | None, window_years: float) -> dict:
    """All returned figures are annualized rolling-CAGR percentages (not raw
    fractions), consistent with `compute_returns`'s `cagr_pct` fields."""
    roll = rolling_returns(nav, window_years)
    distribution = _distribution_to_pct(rolling_return_distribution(roll))

    consistency = None
    if benchmark is not None and not benchmark.empty and not roll.empty:
        bench_roll = rolling_returns(benchmark, window_years)
        consistency = _consistency_to_pct(benchmark_consistency(roll, bench_roll))

    return {
        "window_years": window_years,
        "available": not roll.empty,
        "reason": None if not roll.empty else "insufficient_history",
        "distribution": distribution,
        "benchmark_consistency": consistency,
    }


def compute_rolling_return_series(nav: pd.Series, window: str, lookback: str) -> dict:
    """A plottable time series for the rolling-return bar chart: one point
    per (downsampled) start date, each the rolling return for `window`
    ending on that date. Unlike `compute_rolling_returns`, this returns the
    actual series, not a distribution summary.

    `window` selects the rolling window length (1m/3m/6m/1y — sub-annual
    windows report a non-annualized simple return, see
    analytics/rolling_returns.py); `lookback` trims that series down to
    only the most recent 1/3/5/10 years' worth of start dates, so a fund
    with more history than the chosen lookback doesn't dump years of
    now-irrelevant bars into the chart.

    `available: False` means there isn't enough NAV history for even one
    `window`-length rolling return yet — not that the lookback trimmed
    everything away (a fund with less history than the lookback still
    returns whatever points it has, covering its actual available span).
    """
    window_years = ROLLING_SERIES_WINDOWS_YEARS[window]
    lookback_years = ROLLING_SERIES_LOOKBACK_YEARS[lookback]

    roll = rolling_returns(nav, window_years)
    if roll.empty:
        return {
            "window": window,
            "lookback": lookback,
            "window_years": window_years,
            "annualized": window_years >= 1,
            "available": False,
            "reason": "insufficient_history",
            "points": [],
        }

    cutoff = roll.index[-1] - pd.Timedelta(days=round(lookback_years * 365.25))
    windowed = roll.loc[roll.index >= cutoff]

    # Target roughly one bar per `window` of calendar time within the
    # lookback (lookback_years / window_years — e.g. 1y/1m = 12), clamped
    # to [MIN_ROLLING_SERIES_POINTS, MAX_ROLLING_SERIES_POINTS] so the
    # chart never collapses to a handful of bars or explodes into
    # hundreds. Ceiling division on the resulting step so the sampled
    # count never exceeds the target (floor division under-steps
    # whenever len(windowed) isn't an exact multiple of it).
    target_points = max(MIN_ROLLING_SERIES_POINTS, min(MAX_ROLLING_SERIES_POINTS, round(lookback_years / window_years)))
    step = max(1, -(-len(windowed) // target_points))
    sampled = windowed.iloc[::step]

    return {
        "window": window,
        "lookback": lookback,
        "window_years": window_years,
        "annualized": window_years >= 1,
        "available": True,
        "reason": None,
        "points": [{"date": _to_date(idx), "return_pct": round(float(v) * 100, 4)} for idx, v in sampled.items()],
    }


def compute_drawdown(nav: pd.Series) -> dict:
    if len(nav) < MIN_OBSERVATIONS_FOR_RISK:
        return {
            "available": False, "reason": "insufficient_history",
            "max_drawdown_pct": None, "peak_date": None, "peak_nav": None,
            "trough_date": None, "trough_nav": None, "recovered": None,
            "recovery_date": None, "recovery_duration_days": None,
        }
    result = max_drawdown(nav)
    return {
        "available": True,
        "reason": None,
        "max_drawdown_pct": round(result["max_drawdown_pct"] * 100, 4),
        "peak_date": _to_date(result["peak_date"]),
        "peak_nav": round(result["peak_nav"], 4),
        "trough_date": _to_date(result["trough_date"]),
        "trough_nav": round(result["trough_nav"], 4),
        "recovered": result["recovered"],
        "recovery_date": _to_date(result["recovery_date"]),
        "recovery_duration_days": result["recovery_duration_days"],
    }
