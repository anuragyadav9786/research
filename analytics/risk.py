"""Volatility, Sharpe and Sortino ratio calculations.

Risk-free rate methodology (applies to `sharpe_ratio` and `sortino_ratio`):
the caller always passes an explicit annual risk-free rate — this module
never hard-codes one. In the API/service layer that value currently comes
from `Settings.risk_free_rate` (backend/app/core/config.py), a manually
configured constant documented as a placeholder until a real feed (e.g. RBI
91-day T-bill rate) is ingested — see docs/BUILD_PLAN.md open decision #4.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = 252  # trading days; documented assumption for all "annualized" figures below


def annualized_volatility(daily_returns: pd.Series, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Annualized standard deviation of returns.

    Formula: std(daily_returns, ddof=1) * sqrt(periods_per_year)

    ddof=1 (sample standard deviation) is used because daily_returns is a
    sample of a fund's return-generating process, not the full population.

    Limitations: requires at least 2 observations; assumes returns are
    i.i.d., which real fund returns are not (they exhibit volatility
    clustering) — this is a standard simplification, not a claim of
    statistical precision.
    """
    if len(daily_returns) < 2:
        raise ValueError("need at least 2 return observations")
    return float(daily_returns.std(ddof=1) * np.sqrt(periods_per_year))


def downside_deviation(daily_returns: pd.Series, target_daily_return: float = 0.0,
                        periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Annualized downside deviation relative to a target return.

    Formula: sqrt(mean(min(r - target, 0)^2)) * sqrt(periods_per_year)

    Only returns below `target_daily_return` contribute; returns at or
    above the target contribute zero (not negative contribution — this is
    what distinguishes downside deviation from ordinary standard deviation).

    `target_daily_return` defaults to 0 (i.e. "any loss counts"); pass the
    daily-equivalent risk-free rate to compute the Sortino ratio's
    denominator instead — see `sortino_ratio`.
    """
    if len(daily_returns) < 2:
        raise ValueError("need at least 2 return observations")
    downside = np.minimum(daily_returns - target_daily_return, 0.0)
    return float(np.sqrt(np.mean(downside**2)) * np.sqrt(periods_per_year))


def _annual_to_daily_rate(annual_rate: float, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    return (1.0 + annual_rate) ** (1.0 / periods_per_year) - 1.0


def sharpe_ratio(daily_returns: pd.Series, risk_free_rate_annual: float,
                  periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Sharpe ratio: risk-adjusted excess return per unit of total volatility.

    Formula: mean(daily_returns - daily_risk_free) / std(daily_returns, ddof=1)
             * sqrt(periods_per_year)

    The annual risk-free rate is converted to a compounding-consistent daily
    rate via `_annual_to_daily_rate` (not simply divided by 252), then
    subtracted per-period before annualizing — this keeps the ratio
    dimensionally consistent (both numerator and denominator use daily
    figures, then are annualized together).

    Interpretation: higher is better; > 1 is generally considered good,
    > 2 very good, by common (not universal) convention.

    Limitations: penalizes upside volatility exactly as much as downside
    volatility, which is why `sortino_ratio` is reported alongside it.
    """
    if len(daily_returns) < 2:
        raise ValueError("need at least 2 return observations")
    daily_rf = _annual_to_daily_rate(risk_free_rate_annual, periods_per_year)
    excess = daily_returns - daily_rf
    std = daily_returns.std(ddof=1)
    if std == 0:
        raise ValueError("cannot compute Sharpe ratio: zero return volatility")
    return float(excess.mean() / std * np.sqrt(periods_per_year))


def sortino_ratio(daily_returns: pd.Series, risk_free_rate_annual: float,
                   periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Sortino ratio: risk-adjusted excess return per unit of downside risk.

    Formula: (mean_daily_return - daily_risk_free) * periods_per_year
             / downside_deviation(daily_returns, target=daily_risk_free)

    The risk-free rate serves double duty here (as in most published
    methodologies): it is both the return being exceeded in the numerator
    and the target defining "downside" in the denominator's downside
    deviation. This is a documented choice, not the only valid one — some
    methodologies use 0% or a separate MAR (minimum acceptable return) for
    the denominator target.

    Limitations: if the fund never had a return below the risk-free rate in
    the sample window, downside deviation is 0 and the ratio is undefined
    (raises ValueError) rather than silently returning infinity.
    """
    if len(daily_returns) < 2:
        raise ValueError("need at least 2 return observations")
    daily_rf = _annual_to_daily_rate(risk_free_rate_annual, periods_per_year)
    dd = downside_deviation(daily_returns, target_daily_return=daily_rf, periods_per_year=periods_per_year)
    if dd == 0:
        raise ValueError("cannot compute Sortino ratio: zero downside deviation in sample")
    annualized_excess_return = (daily_returns.mean() - daily_rf) * periods_per_year
    return float(annualized_excess_return / dd)
