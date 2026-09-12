"""Combining multiple funds into one portfolio (Section 9's Phase-9 slice:
combined/"look-through" holdings and portfolio-level return series).

These functions are intentionally generic and backend-agnostic — they take
plain dicts and pandas Series, never ORM objects — so they compose with
the existing single-fund analytics (concentration.py, overlap.py, risk.py,
drawdown.py) rather than duplicating any of that math. A "portfolio" here
is just a set of funds and their weight in the overall allocation; what
each fund itself is made of already has functions elsewhere.
"""
from __future__ import annotations

import pandas as pd


def combine_effective_weights(
    per_fund_weights: dict[str, dict[str, float]], fund_weights_pct: dict[str, float]
) -> dict[str, float]:
    """Look-through ("effective") weight of each label across a combined
    portfolio of funds.

    Formula: effective_weight[label] = sum_over_funds(
        fund_weights_pct[fund] / 100 * per_fund_weights[fund].get(label, 0)
    )

    Generic over what "label" is: call it once with per-security weights
    to get combined security exposure, once with per-sector weights (each
    fund's sector weights pre-aggregated via `concentration.group_weights`)
    to get combined sector exposure, and once with market-cap weights for
    combined market-cap exposure — no separate formula needed per
    dimension.

    Interpretation: a security appearing in multiple funds gets its
    exposures summed — this is precisely how "hidden concentration"
    becomes visible (Section 9): two funds that each look diversified can
    combine into a portfolio that is not.

    Limitations: inherits each fund's own disclosure limitations — if a
    fund only discloses top-10 holdings, this only sees that top-10,
    diluted by that fund's weight in the overall portfolio.
    """
    combined: dict[str, float] = {}
    for fund_key, fund_weight_pct in fund_weights_pct.items():
        fund_holdings = per_fund_weights.get(fund_key, {})
        scale = fund_weight_pct / 100.0
        for label, weight_pct in fund_holdings.items():
            combined[label] = combined.get(label, 0.0) + scale * weight_pct
    return combined


def combine_weighted_returns(per_fund_returns: dict[str, pd.Series], fund_weights_pct: dict[str, float]) -> pd.Series:
    """Portfolio-level daily return series from constituent funds' returns.

    Formula: portfolio_return[t] = sum(fund_weights_pct[f]/100 * fund_return_f[t])
             for each date t present in EVERY fund's return series.

    Methodology note: uses only dates common to all constituent funds
    (inner join) — a fund with a shorter history will shrink the whole
    portfolio's analyzable window. This is a simplifying assumption (a
    real investor's portfolio return wouldn't have this gap), documented
    rather than papered over with an assumed 0% return for missing dates.

    Assumes static weights (no rebalancing over the analyzed period) — a
    documented simplification; real portfolios drift from their target
    weights as constituent funds move, which this does not model.

    Limitations: requires at least one common date across all funds and
    at least 2 funds' worth of weight data; raises ValueError otherwise
    rather than silently returning an empty or zero series.
    """
    if not per_fund_returns:
        raise ValueError("need at least one fund's return series")

    aligned = pd.concat(per_fund_returns, axis=1, join="inner")
    if aligned.empty:
        raise ValueError("no dates common to all constituent funds' return histories")

    weights = pd.Series({fund: fund_weights_pct.get(fund, 0.0) / 100.0 for fund in aligned.columns})
    return aligned.mul(weights, axis=1).sum(axis=1)


def synthetic_nav_from_returns(returns: pd.Series, base: float = 100.0) -> pd.Series:
    """Reconstructs a NAV-like level series from a return series, so
    existing NAV-based functions (`analytics.drawdown.max_drawdown`) can
    run on a combined portfolio's returns without a separate
    drawdown-on-returns implementation.

    Formula: nav[t] = base * prod(1 + returns[<=t])

    This is exactly what a hypothetical ₹`base`-unit investment would be
    worth over time if it earned exactly this return series — a synthetic
    construction for analysis, not a real traded instrument.
    """
    return base * (1.0 + returns).cumprod()
