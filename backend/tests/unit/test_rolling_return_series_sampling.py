"""Unit tests for compute_rolling_return_series' downsampling cadence and
date alignment — fixes for two real reported bugs:

1. Bar COUNT: choosing a different `window` (1m/3m/6m/1y) at a fixed
   `lookback` used to leave the chart's bar count visually unchanged,
   because sampling was downsampled evenly to a flat cap
   (MAX_ROLLING_SERIES_POINTS) regardless of window length, even though
   each bar's VALUE was correctly computed for the chosen window. Sampling
   cadence now targets roughly lookback/window bars, so switching windows
   visibly changes the chart, clamped to [MIN_ROLLING_SERIES_POINTS,
   MAX_ROLLING_SERIES_POINTS].

2. Bar DATES: two funds, same window/lookback choice, viewed the same
   day, used to show bars on completely different calendar dates — bars
   were sampled by position starting from each fund's own last valid
   rolling-window start, which is itself a function of that fund's own
   last NAV date (NAV history is backfilled/refreshed per-fund
   independently, see lazy_nav_backfill.py). Bars are now sampled by
   walking backward from a shared `today` anchor and asof-matching each
   calendar target to each fund's nearest actual data — see
   compute_rolling_return_series's own docstring.
"""
from datetime import date, timedelta

import pandas as pd

from app.services.fund_analytics_service import (
    MAX_ROLLING_SERIES_POINTS,
    MIN_ROLLING_SERIES_POINTS,
    compute_rolling_return_series,
)


_FIXTURE_TODAY = date(2026, 9, 21)


def _daily_nav(years: float, start_value: float = 100.0, end_date: date = _FIXTURE_TODAY) -> pd.Series:
    """~`years` of daily NAV with a slight upward drift and small day-to-
    day noise (deterministic, no randomness) so rolling returns are
    genuinely computable and non-degenerate across the whole span.
    `end_date` is overridable so a test can build two funds whose NAV
    history ends on different real dates — the exact scenario the
    calendar-anchored-to-today fix (compute_rolling_return_series's
    `today` parameter) targets."""
    n_days = round(years * 365.25)
    dates = pd.date_range(end=end_date, periods=n_days, freq="D")
    values = [start_value * (1.00015**i) * (1 + 0.001 * ((i % 7) - 3)) for i in range(n_days)]
    return pd.Series(values, index=dates)


def test_shorter_window_produces_more_bars_at_the_same_lookback():
    nav = _daily_nav(years=2.0)

    one_month = compute_rolling_return_series(nav, window="1m", lookback="1y", today=_FIXTURE_TODAY)
    three_month = compute_rolling_return_series(nav, window="3m", lookback="1y", today=_FIXTURE_TODAY)
    one_year = compute_rolling_return_series(nav, window="1y", lookback="1y", today=_FIXTURE_TODAY)

    assert one_month["available"] and three_month["available"] and one_year["available"]
    counts = [len(one_month["points"]), len(three_month["points"]), len(one_year["points"])]
    # The whole point of the fix: these must differ, not collapse to the
    # same downsampled count regardless of which window was picked.
    assert len(set(counts)) > 1
    assert counts[0] > counts[1] > counts[2]


def test_one_month_window_over_one_year_lookback_gives_about_twelve_bars():
    nav = _daily_nav(years=2.0)
    result = compute_rolling_return_series(nav, window="1m", lookback="1y", today=_FIXTURE_TODAY)
    # Exactly matches the reported expectation: "if I select a 1-month
    # rolling window for the last 1 year, it should present ~12 bars."
    assert 10 <= len(result["points"]) <= 14


def test_bar_count_stays_within_configured_bounds_across_every_combination():
    nav = _daily_nav(years=11.0)  # long enough to exercise every lookback option fully
    for window in ("1m", "3m", "6m", "1y"):
        for lookback in ("1y", "3y", "5y", "10y"):
            result = compute_rolling_return_series(nav, window=window, lookback=lookback, today=_FIXTURE_TODAY)
            assert result["available"], f"{window}/{lookback} should have data with 11y of history"
            count = len(result["points"])
            assert MIN_ROLLING_SERIES_POINTS <= count <= MAX_ROLLING_SERIES_POINTS, (window, lookback, count)


def test_longer_lookback_produces_more_bars_at_the_same_window():
    nav = _daily_nav(years=6.0)
    one_year = compute_rolling_return_series(nav, window="3m", lookback="1y", today=_FIXTURE_TODAY)
    five_year = compute_rolling_return_series(nav, window="3m", lookback="5y", today=_FIXTURE_TODAY)
    assert len(five_year["points"]) > len(one_year["points"])


def test_two_funds_with_different_last_nav_dates_share_bar_dates_given_the_same_today():
    """The reported bug, directly: two funds viewed on the same day, with
    the same window/lookback choice, used to show bars on different
    calendar dates purely because their NAV history happened to end on
    different days (NAV is backfilled/refreshed per-fund, see
    lazy_nav_backfill.py — this is routine, not a data quality issue).
    Anchoring to a shared `today` instead of each fund's own last NAV date
    fixes that: every bar except each fund's own most-recent one (which
    legitimately reflects each fund's own latest available data) must
    land on the identical calendar date."""
    today = date(2026, 10, 8)
    fund_a = _daily_nav(years=3.0, end_date=date(2026, 9, 30))  # 8 days stale
    fund_b = _daily_nav(years=3.0, end_date=date(2026, 10, 8))  # fresh

    result_a = compute_rolling_return_series(fund_a, window="3m", lookback="1y", today=today)
    result_b = compute_rolling_return_series(fund_b, window="3m", lookback="1y", today=today)

    assert result_a["available"] and result_b["available"]
    starts_a = [p["start_date"] for p in result_a["points"]]
    starts_b = [p["start_date"] for p in result_b["points"]]
    assert len(starts_a) == len(starts_b)
    # Every bar but the very last (most recent) one lines up exactly.
    assert starts_a[:-1] == starts_b[:-1]
    # The last bar is allowed to differ — each fund's own true latest data.
    assert starts_a[-1] != starts_b[-1]


def test_a_real_gap_near_the_recent_end_produces_fewer_deduped_bars_not_fabricated_ones():
    """The HDFC Flexi Cap precedent (see
    _MAX_PLAUSIBLE_WINDOW_SLIPPAGE_DAYS's docstring): a fund with a real,
    long NAV gap close to `today` must not show duplicate or fabricated
    bars for the calendar targets that fall inside the gap — they should
    all collapse to the single real start date on the near side of the
    gap, and the chart should simply show fewer bars than usual."""
    today = date(2026, 10, 8)
    pre_gap = pd.date_range(end=date(2022, 1, 1), periods=round(8 * 365.25), freq="D")
    post_gap = pd.date_range(start=date(2026, 9, 1), end=today, freq="D")  # 38-day post-gap tail
    dates = pre_gap.append(post_gap)
    values = (
        [100 + 0.01 * i for i in range(len(pre_gap))]
        + [100 + 0.01 * len(pre_gap) + 0.01 * i for i in range(len(post_gap))]
    )
    nav = pd.Series(values, index=dates)

    result = compute_rolling_return_series(nav, window="3m", lookback="1y", today=today)

    assert result["available"]
    # The 38-day post-gap tail is too short for even one 3-month window to
    # complete — every post-gap calendar target asof-matches the same
    # single pre-gap start, so dedup must collapse them to exactly one
    # bar, not several identical-looking ones, and never raise.
    assert len(result["points"]) == 1
    starts = [p["start_date"] for p in result["points"]]
    assert len(starts) == len(set(starts))


def test_window_equals_lookback_still_respects_the_minimum_bar_count():
    """window="1y"/lookback="1y" is the one combination where window_years
    equals lookback_years (the only pair in ROLLING_SERIES_WINDOWS_YEARS/
    ROLLING_SERIES_LOOKBACK_YEARS where this happens) — a structural edge
    case where spacing bars a full window-length apart would only fit 1-2
    bars in a 1-year lookback, undershooting MIN_ROLLING_SERIES_POINTS.
    Confirms the fix still reaches the floor, with distinct, chronological
    start dates."""
    nav = _daily_nav(years=11.0)
    result = compute_rolling_return_series(nav, window="1y", lookback="1y", today=_FIXTURE_TODAY)

    assert result["available"]
    assert len(result["points"]) == MIN_ROLLING_SERIES_POINTS
    starts = [p["start_date"] for p in result["points"]]
    assert starts == sorted(starts)
    assert len(starts) == len(set(starts))
