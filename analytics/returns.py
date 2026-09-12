"""Absolute return and CAGR calculations.

All functions here are pure and deterministic: given the same NAV inputs
they always return the same output. No network access, no randomness, no
LLM involvement — see Rule 4 in the project brief. Full methodology write-up
lives in docs/analytics-methodology.md.
"""
from __future__ import annotations

import pandas as pd


def simple_return(nav_start: float, nav_end: float) -> float:
    """Point-to-point (non-annualized) return.

    Formula: (nav_end / nav_start) - 1

    Interpretation: total return earned over the period, not adjusted for
    its length. Use for periods of one year or less; for longer periods,
    prefer `cagr` so returns of different lengths are comparable.
    """
    if nav_start <= 0:
        raise ValueError("nav_start must be positive")
    return (nav_end / nav_start) - 1.0


def cagr(nav_start: float, nav_end: float, years: float) -> float:
    """Compound Annual Growth Rate.

    Formula: (nav_end / nav_start) ** (1 / years) - 1

    Input: starting NAV, ending NAV, and the elapsed time in years
    (fractional years allowed, e.g. 547 days / 365.25).

    Interpretation: the constant annual growth rate that would take
    nav_start to nav_end over the given period. This is what should be
    shown for any period longer than one year — raw simple returns over
    multi-year periods are not comparable across funds with different
    starting/ending dates.

    Limitations: undefined for years <= 0 or nav_start <= 0; meaningless
    for periods shorter than ~1 year (small denominators amplify noise into
    absurd annualized figures) — callers should use `simple_return` for
    sub-annual periods instead.
    """
    if nav_start <= 0:
        raise ValueError("nav_start must be positive")
    if years <= 0:
        raise ValueError("years must be positive")
    return (nav_end / nav_start) ** (1.0 / years) - 1.0


def returns_series(nav: pd.Series) -> pd.Series:
    """Periodic (e.g. daily) simple returns from a NAV series indexed by date.

    Formula: nav.pct_change(), first observation dropped (no prior NAV to
    compare against).
    """
    if nav.empty:
        return nav.copy()
    return nav.sort_index().pct_change().dropna()


def cagr_for_window(nav: pd.Series, start_date, end_date) -> float | None:
    """CAGR for the NAV series restricted to [start_date, end_date].

    Returns None if either endpoint has no NAV observation on/near it in the
    series (rather than silently guessing a nearby date — see Rule on never
    inserting unvalidated data).
    """
    nav = nav.sort_index()
    window = nav.loc[start_date:end_date]
    if window.empty or len(window) < 2:
        return None
    nav_start, nav_end = window.iloc[0], window.iloc[-1]
    days = (window.index[-1] - window.index[0]).days
    if days <= 0:
        return None
    years = days / 365.25
    return cagr(nav_start, nav_end, years)
