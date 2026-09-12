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


def _to_date(value) -> date | None:
    if value is None:
        return None
    return pd.Timestamp(value).date()


def compute_returns(nav: pd.Series) -> dict:
    if nav.empty:
        return {
            "as_of_date": None,
            "windows": {
                label: {"available": False, "cagr_pct": None, "start_date": None, "end_date": None,
                        "reason": "no_nav_history"}
                for label in RETURN_WINDOWS_YEARS
            },
        }

    end_date = nav.index[-1]
    windows = {}
    for label, years in RETURN_WINDOWS_YEARS.items():
        target_start = end_date - pd.Timedelta(days=round(years * 365.25))
        if target_start < nav.index[0]:
            windows[label] = {
                "available": False, "cagr_pct": None, "start_date": None, "end_date": None,
                "reason": "insufficient_history",
            }
            continue
        window_nav = nav.loc[target_start:end_date]
        cagr_value = cagr_for_window(nav, target_start, end_date)
        if cagr_value is None:
            windows[label] = {
                "available": False, "cagr_pct": None, "start_date": None, "end_date": None,
                "reason": "insufficient_history",
            }
        else:
            windows[label] = {
                "available": True,
                "cagr_pct": round(cagr_value * 100, 4),
                "start_date": _to_date(window_nav.index[0]),
                "end_date": _to_date(end_date),
                "reason": None,
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
