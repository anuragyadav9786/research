"""Per-regime fund behaviour (Section 7: Market-Cycle Behaviour Engine).

Computes how a NAV series behaved during a specific date window (a "market
regime" — bull, correction, high volatility, etc., as defined in the
`market_regimes` reference table) by reusing the existing single-fund
analytics rather than inventing regime-specific formulas: a regime is just
a date range, and "how did the fund do in this date range" is the same
question `analytics.returns`, `analytics.risk` and `analytics.drawdown`
already answer for any window.
"""
from __future__ import annotations

import pandas as pd

from analytics.drawdown import max_drawdown
from analytics.returns import returns_series, simple_return
from analytics.risk import annualized_volatility

MIN_OBSERVATIONS = 2


def regime_metrics(nav: pd.Series, start, end) -> dict:
    """Return, volatility and max drawdown for a NAV series restricted to
    [start, end].

    Formula: simple (non-annualized) point-to-point return over the
    window — regimes are often shorter than a year, where CAGR would be
    misleading (see `analytics.returns.cagr`'s own documented limitation
    on sub-annual periods), so this deliberately does not annualize the
    return the way `analytics.returns.cagr_for_window` does. Volatility is
    still annualized (that's a rate, not a total), computed only if the
    window has at least 2 return observations.

    Returns `available: False` (never a fabricated 0%) if the NAV series
    has fewer than 2 observations inside the window — e.g. NAV history
    starting after the regime already began.
    """
    window = nav.sort_index().loc[pd.Timestamp(start):pd.Timestamp(end)]
    if len(window) < MIN_OBSERVATIONS:
        return {
            "available": False,
            "observations": len(window),
            "return_pct": None,
            "volatility_pct": None,
            "max_drawdown_pct": None,
        }

    return_pct = simple_return(window.iloc[0], window.iloc[-1]) * 100

    window_returns = returns_series(window)
    volatility_pct = (
        annualized_volatility(window_returns) * 100 if len(window_returns) >= MIN_OBSERVATIONS else None
    )

    drawdown_pct = max_drawdown(window)["max_drawdown_pct"] * 100

    return {
        "available": True,
        "observations": len(window),
        "return_pct": return_pct,
        "volatility_pct": volatility_pct,
        "max_drawdown_pct": drawdown_pct,
    }
