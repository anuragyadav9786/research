"""Lumpsum and SIP investment-value projections against a real NAV series.

Answers "what would this investment be worth today", in rupee terms — a
different question from returns.py's CAGR (the annualized rate), for a
specific amount and, for SIP, a specific contribution frequency. Every
figure here is computed directly from real recorded NAV observations
(pandas' own `.asof` — the last trading-day NAV on/before a given date,
the same nearest-prior-trading-day convention already used elsewhere in
this codebase, e.g. rolling_returns.rolling_window_end_date); nothing is
interpolated or invented.

Pure and deterministic, same as every other module here: no network
access, no randomness (Rule 4 in the project brief).
"""
from __future__ import annotations

import pandas as pd

SIP_FREQUENCIES = ("daily", "weekly", "monthly")


def lumpsum_value(nav: pd.Series, start_date, end_date, amount: float) -> float | None:
    """Value today of `amount` invested as a single lumpsum on start_date,
    redeemed on end_date: amount * (nav_end / nav_start) — the exact
    growth ratio between the two real NAV observations, not derived from
    a rounded CAGR percentage. None if the window has fewer than two NAV
    observations (no valid start/end pair to compute a ratio from).
    """
    nav = nav.sort_index()
    window = nav.loc[start_date:end_date]
    if window.empty or len(window) < 2:
        return None
    return amount * (float(window.iloc[-1]) / float(window.iloc[0]))


def sip_value(nav: pd.Series, start_date, end_date, installment_amount: float, frequency: str) -> dict | None:
    """Value today of a fixed `installment_amount` invested every
    `frequency` period from start_date through end_date.

    "daily" invests on every actual trading day the NAV series has in the
    window — never a calendar day with no NAV to buy at. "weekly"/"monthly"
    schedule a fixed calendar-date cadence starting from start_date, and
    each installment buys at the last available NAV on/before its
    scheduled date (nav.asof) — a scheduled date that falls on a
    non-trading day (weekend/holiday) uses the prior trading day's NAV,
    never an interpolated one.

    Returns None if the window has no NAV observations at all, or if
    `frequency` isn't one of SIP_FREQUENCIES.
    """
    if frequency not in SIP_FREQUENCIES:
        return None

    nav = nav.sort_index()
    window = nav.loc[start_date:end_date]
    if window.empty:
        return None

    if frequency == "daily":
        installment_navs = [float(v) for v in window.values]
    else:
        step = pd.Timedelta(days=7) if frequency == "weekly" else None
        dates: list[pd.Timestamp] = []
        d = window.index[0]
        while d <= window.index[-1]:
            dates.append(d)
            d = d + step if step is not None else d + pd.DateOffset(months=1)
        installment_navs = []
        for d in dates:
            v = nav.asof(d)
            if v is not None and not pd.isna(v):
                installment_navs.append(float(v))

    if not installment_navs:
        return None

    total_units = sum(installment_amount / v for v in installment_navs)
    nav_end = float(window.iloc[-1])
    return {
        "installments": len(installment_navs),
        "invested_amount": installment_amount * len(installment_navs),
        "value": total_units * nav_end,
    }
