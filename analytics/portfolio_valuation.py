"""Reconstructs a portfolio's own actual value over time from each holding's
real transaction history, and derives a Time-Weighted Return (TWR) from it.

Distinct from `analytics/portfolio.py`'s `combine_weighted_returns`, which
assumes FIXED weights throughout (a hypothetical "what if I'd held these
funds at these weights the whole time" combination, used by the manual
multi-fund Portfolio Analysis flow). Here, weights are whatever the real
investor's own purchases/redemptions/switches actually produced at every
point in time — the basis for the *actual* portfolio's TWR, volatility, and
drawdown, as opposed to any one constituent fund's or a hypothetical
static-weight blend's.

TWR (not XIRR) is the right lens for volatility/drawdown: XIRR (analytics/
xirr.py) answers "what annualized return did MY money actually earn,
given when I put it in," which is sensitive to the investor's own cash-flow
timing. TWR strips that out — chain-linking sub-period returns so a big
SIP addition right before a market dip doesn't itself register as a loss —
which is what a peak-to-trough drawdown or period-to-period volatility
figure needs to mean "how choppy was the ride," not "how did this
investor's timing luck play out."

Pure and deterministic: no network access, no randomness (Rule 4 in the
project brief).
"""
from __future__ import annotations

from datetime import date

import pandas as pd


def units_held_series(nav_index: pd.DatetimeIndex, unit_events: list[tuple[date, float]]) -> pd.Series:
    """Cumulative units held on each date in `nav_index`, replayed from a
    list of signed (date, units_delta) events — the same sign convention
    CAS transactions themselves use (positive = units added, negative =
    units removed). Units held before any event is 0, never guessed. An
    event on a date not present in `nav_index` (e.g. no NAV published that
    day) still takes effect from the next date in `nav_index` onward."""
    if not unit_events:
        return pd.Series(0.0, index=nav_index)

    deltas: dict[pd.Timestamp, float] = {}
    for event_date, units in unit_events:
        ts = pd.Timestamp(event_date)
        deltas[ts] = deltas.get(ts, 0.0) + units
    delta_series = pd.Series(deltas).sort_index()

    combined_index = nav_index.union(delta_series.index)
    cumulative = delta_series.reindex(combined_index, fill_value=0.0).cumsum()
    return cumulative.reindex(nav_index).ffill().fillna(0.0)


def combine_portfolio_value_series(per_scheme_value: dict[str, pd.Series]) -> pd.Series:
    """Sums each scheme's own value series onto the union of every scheme's
    own valuation dates. A scheme contributes 0 before its own first NAV
    date (never backfilled/guessed at a value before we have one) and, once
    it has a value, holds its last-known figure between its own NAV
    publication dates (ffill) — the same "value persists until the next
    known data point" assumption `analytics/drawdown.py` and the rest of
    this codebase's NAV-based functions already make."""
    if not per_scheme_value:
        return pd.Series(dtype=float)

    union_index: pd.DatetimeIndex | None = None
    for series in per_scheme_value.values():
        union_index = series.index if union_index is None else union_index.union(series.index)

    aligned = [series.reindex(union_index).ffill().fillna(0.0) for series in per_scheme_value.values()]
    combined = aligned[0]
    for series in aligned[1:]:
        combined = combined.add(series)
    return combined.sort_index()


def daily_net_contributions(nav_index: pd.DatetimeIndex, contribution_events: list[tuple[date, float]]) -> pd.Series:
    """Net external cash CONTRIBUTED by the investor on each date in
    `nav_index` — positive = money invested that day, negative = money
    withdrawn. This is the opposite sign convention from `analytics/
    xirr.py`'s cash flows (there, negative = money leaving the investor's
    pocket); here, positive = money leaving the investor's pocket INTO the
    portfolio, which is what the TWR formula below needs. Switches/STP
    between schemes already inside the portfolio are internal transfers,
    not contributions — callers exclude them from `contribution_events`
    before calling this, same boundary the portfolio XIRR cash flows use."""
    deltas: dict[pd.Timestamp, float] = {}
    for event_date, amount in contribution_events:
        ts = pd.Timestamp(event_date)
        deltas[ts] = deltas.get(ts, 0.0) + amount
    series = pd.Series(deltas, dtype=float) if deltas else pd.Series(dtype=float)
    return series.reindex(nav_index, fill_value=0.0)


def cash_flow_adjusted_returns(value: pd.Series, contributions: pd.Series) -> pd.Series:
    """Time-weighted (cash-flow-neutralized) sub-period returns.

    Formula (the "True Daily Valuation Method," the standard cash-flow-
    neutral TWR construction when a value can be struck on every date):
    r_t = (V_t - CF_t) / V_(t-1) - 1, where CF_t is the net external
    contribution ON DAY t (already reflected in V_t, since V_t is valued
    using post-transaction unit holdings) — this neutralizes a same-day
    contribution or withdrawal so it never itself registers as a gain or
    loss.

    Days before the portfolio's first-ever holding (V_(t-1) == 0, nothing
    yet invested) are dropped, never treated as a fabricated 0% return —
    there is nothing to have had a return on yet.
    """
    value = value.sort_index()
    contributions = contributions.reindex(value.index, fill_value=0.0)
    prev_value = value.shift(1)
    returns = (value - contributions) / prev_value - 1.0
    return returns[prev_value > 0].dropna()


def time_weighted_return(returns: pd.Series) -> float | None:
    """Cumulative time-weighted return: chain-link every sub-period return.
    None if there are no valid sub-periods to chain (e.g. under 1 day of
    reconstructable history)."""
    if returns.empty:
        return None
    return float((1.0 + returns).prod() - 1.0)


def annualized_time_weighted_return(cumulative_twr: float, start_date: date, end_date: date) -> float | None:
    """Annualizes a cumulative TWR over the actual elapsed span it covers.
    None if the span is zero or negative days (can't annualize a point)."""
    days = (end_date - start_date).days
    if days <= 0:
        return None
    return (1.0 + cumulative_twr) ** (365.0 / days) - 1.0
