"""Unit tests for compute_rolling_return_series' downsampling cadence —
the fix for a real reported bug: choosing a different `window` (1m/3m/
6m/1y) at a fixed `lookback` used to leave the chart's bar COUNT visually
unchanged, because sampling was downsampled evenly to a flat cap
(MAX_ROLLING_SERIES_POINTS) regardless of window length, even though each
bar's VALUE was correctly computed for the chosen window. Sampling cadence
now targets roughly lookback/window bars, so switching windows visibly
changes the chart, clamped to [MIN_ROLLING_SERIES_POINTS,
MAX_ROLLING_SERIES_POINTS].
"""
from datetime import date, timedelta

import pandas as pd

from app.services.fund_analytics_service import (
    MAX_ROLLING_SERIES_POINTS,
    MIN_ROLLING_SERIES_POINTS,
    compute_rolling_return_series,
)


def _daily_nav(years: float, start_value: float = 100.0) -> pd.Series:
    """~`years` of daily NAV with a slight upward drift and small day-to-
    day noise (deterministic, no randomness) so rolling returns are
    genuinely computable and non-degenerate across the whole span."""
    n_days = round(years * 365.25)
    dates = pd.date_range(end=date(2026, 9, 21), periods=n_days, freq="D")
    values = [start_value * (1.00015**i) * (1 + 0.001 * ((i % 7) - 3)) for i in range(n_days)]
    return pd.Series(values, index=dates)


def test_shorter_window_produces_more_bars_at_the_same_lookback():
    nav = _daily_nav(years=2.0)

    one_month = compute_rolling_return_series(nav, window="1m", lookback="1y")
    three_month = compute_rolling_return_series(nav, window="3m", lookback="1y")
    one_year = compute_rolling_return_series(nav, window="1y", lookback="1y")

    assert one_month["available"] and three_month["available"] and one_year["available"]
    counts = [len(one_month["points"]), len(three_month["points"]), len(one_year["points"])]
    # The whole point of the fix: these must differ, not collapse to the
    # same downsampled count regardless of which window was picked.
    assert len(set(counts)) > 1
    assert counts[0] > counts[1] > counts[2]


def test_one_month_window_over_one_year_lookback_gives_about_twelve_bars():
    nav = _daily_nav(years=2.0)
    result = compute_rolling_return_series(nav, window="1m", lookback="1y")
    # Exactly matches the reported expectation: "if I select a 1-month
    # rolling window for the last 1 year, it should present ~12 bars."
    assert 10 <= len(result["points"]) <= 14


def test_bar_count_stays_within_configured_bounds_across_every_combination():
    nav = _daily_nav(years=11.0)  # long enough to exercise every lookback option fully
    for window in ("1m", "3m", "6m", "1y"):
        for lookback in ("1y", "3y", "5y", "10y"):
            result = compute_rolling_return_series(nav, window=window, lookback=lookback)
            assert result["available"], f"{window}/{lookback} should have data with 11y of history"
            count = len(result["points"])
            assert MIN_ROLLING_SERIES_POINTS <= count <= MAX_ROLLING_SERIES_POINTS, (window, lookback, count)


def test_longer_lookback_produces_more_bars_at_the_same_window():
    nav = _daily_nav(years=6.0)
    one_year = compute_rolling_return_series(nav, window="3m", lookback="1y")
    five_year = compute_rolling_return_series(nav, window="3m", lookback="5y")
    assert len(five_year["points"]) > len(one_year["points"])
