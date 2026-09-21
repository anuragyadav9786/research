"""Unit tests for compute_returns' 3-state return-window status: a window is
either available (VALID), unavailable because the scheme itself hasn't
existed long enough (reason="scheme_too_young"), or unavailable because our
own NAV data for that window is incomplete despite the scheme being old
enough (reason="insufficient_history"). See fund_analytics_service.py's
compute_returns docstring for why the distinction hinges on
nav_history_backfilled (whether mfapi.in's full history has been pulled),
never on a hardcoded or fund-name-derived date.

Named after the exact scenarios in the return-period-status spec."""
from datetime import date, timedelta

import pandas as pd

from app.services.fund_analytics_service import compute_returns


def _daily_nav(start: date, end: date, step_days: int = 5) -> pd.Series:
    dates = pd.date_range(start=start, end=end, freq=f"{step_days}D")
    values = [100.0 * (1.08 ** ((d.date() - start).days / 365.25)) for d in dates]
    return pd.Series(values, index=dates)


def test_case1_scheme_launched_aug_2025_only_1y_calculable():
    """Case 1: scheme launched Aug 2025, valuation Sep 2026 — only the 1Y
    window has enough history; 3Y/5Y/7Y/10Y must be scheme_too_young, never
    insufficient_history, since we've confirmed (via a complete backfill)
    there is no earlier NAV to find."""
    nav = _daily_nav(date(2025, 8, 15), date(2026, 9, 12))
    result = compute_returns(nav, nav_history_backfilled=True)

    assert result["windows"]["1y"]["available"] is True
    for label in ("3y", "5y", "7y", "10y"):
        w = result["windows"][label]
        assert w["available"] is False
        assert w["reason"] == "scheme_too_young"
        assert w["earliest_nav_date"] == date(2025, 8, 15)


def test_case2_scheme_launched_jan_2021_1y_3y_5y_calculable():
    """Case 2: scheme launched Jan 2021, valuation Sep 2026 — 1Y/3Y/5Y
    calculable, 7Y/10Y scheme_too_young."""
    nav = _daily_nav(date(2021, 1, 10), date(2026, 9, 12))
    result = compute_returns(nav, nav_history_backfilled=True)

    for label in ("1y", "3y", "5y"):
        assert result["windows"][label]["available"] is True

    for label in ("7y", "10y"):
        w = result["windows"][label]
        assert w["available"] is False
        assert w["reason"] == "scheme_too_young"
        assert w["earliest_nav_date"] == date(2021, 1, 10)


def test_case3_established_scheme_with_incomplete_nav_history_is_data_unavailable():
    """Case 3 (critical): our own NAV data only reaches back to 2020, and we
    have NOT confirmed (via a complete mfapi.in backfill) that this is the
    scheme's true full history — so the 10Y window must be reported as
    insufficient_history ("Insufficient NAV history"), never scheme_too_young,
    and earliest_nav_date must NOT be surfaced as if it were a launch date."""
    nav = _daily_nav(date(2020, 1, 1), date(2026, 9, 12))
    result = compute_returns(nav, nav_history_backfilled=False)

    w = result["windows"]["10y"]
    assert w["available"] is False
    assert w["reason"] == "insufficient_history"
    assert w["earliest_nav_date"] is None


def test_established_fund_returns_are_unaffected_by_the_new_parameter():
    """A fund with ample real history for every window must show the same
    calculated VALID returns regardless of the backfilled flag — this is a
    presentation-layer change, not a change to the return calculation
    itself."""
    nav = _daily_nav(date(2005, 1, 1), date(2026, 9, 12))
    backfilled = compute_returns(nav, nav_history_backfilled=True)
    not_backfilled = compute_returns(nav, nav_history_backfilled=False)

    for label in ("1y", "3y", "5y", "7y", "10y"):
        assert backfilled["windows"][label]["available"] is True
        assert not_backfilled["windows"][label]["available"] is True
        assert backfilled["windows"][label]["cagr_pct"] == not_backfilled["windows"][label]["cagr_pct"]
        assert backfilled["windows"][label]["reason"] is None


def test_default_backfilled_false_preserves_pre_existing_behaviour():
    """Callers that don't pass nav_history_backfilled (category/discovery
    aggregates) must keep getting exactly the old behaviour: an unavailable
    window is always insufficient_history, never scheme_too_young."""
    nav = _daily_nav(date(2025, 8, 15), date(2026, 9, 12))
    result = compute_returns(nav)

    for label in ("3y", "5y", "7y", "10y"):
        assert result["windows"][label]["reason"] == "insufficient_history"
        assert result["windows"][label]["earliest_nav_date"] is None


def test_empty_nav_history_is_still_no_nav_history_not_scheme_too_young():
    result = compute_returns(pd.Series(dtype=float), nav_history_backfilled=True)
    for label in ("1y", "3y", "5y", "7y", "10y"):
        assert result["windows"][label]["reason"] == "no_nav_history"
        assert result["windows"][label]["earliest_nav_date"] is None
