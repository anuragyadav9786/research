from datetime import date

import pandas as pd
import pytest

from analytics.portfolio_valuation import (
    annualized_time_weighted_return,
    cash_flow_adjusted_returns,
    combine_portfolio_value_series,
    daily_net_contributions,
    time_weighted_return,
    units_held_series,
)


def _idx(*dates: date) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp(d) for d in dates])


def test_units_held_series_zero_before_first_purchase():
    nav_index = _idx(date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3))
    events = [(date(2024, 1, 2), 10.0)]
    result = units_held_series(nav_index, events)
    assert result.tolist() == [0.0, 10.0, 10.0]


def test_units_held_series_replays_purchase_then_redemption():
    nav_index = _idx(date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
    events = [(date(2024, 1, 1), 20.0), (date(2024, 1, 3), -5.0)]
    result = units_held_series(nav_index, events)
    assert result.tolist() == [20.0, 20.0, 15.0, 15.0]


def test_units_held_series_event_on_non_nav_date_takes_effect_from_next_nav_date():
    # A transaction dated a weekend (no NAV published) shows up from the
    # next NAV date onward, not silently dropped.
    nav_index = _idx(date(2024, 1, 1), date(2024, 1, 3))
    events = [(date(2024, 1, 2), 7.0)]
    result = units_held_series(nav_index, events)
    assert result.tolist() == [0.0, 7.0]


def test_combine_portfolio_value_series_sums_across_different_date_ranges():
    a = pd.Series([100.0, 110.0], index=_idx(date(2024, 1, 1), date(2024, 1, 2)))
    # Scheme b starts later -> contributes 0 before its own first date.
    b = pd.Series([50.0], index=_idx(date(2024, 1, 2),))
    combined = combine_portfolio_value_series({"a": a, "b": b})
    assert combined.loc[pd.Timestamp(date(2024, 1, 1))] == pytest.approx(100.0)
    assert combined.loc[pd.Timestamp(date(2024, 1, 2))] == pytest.approx(160.0)


def test_daily_net_contributions_sums_same_day_events_and_zero_fills_others():
    nav_index = _idx(date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3))
    events = [(date(2024, 1, 1), 1000.0), (date(2024, 1, 1), 500.0)]  # two same-day purchases
    result = daily_net_contributions(nav_index, events)
    assert result.tolist() == [1500.0, 0.0, 0.0]


def test_cash_flow_adjusted_returns_neutralizes_same_day_contribution():
    # Day 0: invest 1000 (initial value struck at 1000, nothing before it).
    # Day 1: market +10% -> 1100.
    # Day 2: invest another 500 with the market flat that day -> value 1600.
    # Day 3: market -5% -> 1520.
    dates = _idx(date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
    value = pd.Series([1000.0, 1100.0, 1600.0, 1520.0], index=dates)
    contributions = pd.Series([1000.0, 0.0, 500.0, 0.0], index=dates)

    returns = cash_flow_adjusted_returns(value, contributions)

    # Day 0 dropped: nothing held the day before -> no return to compute yet.
    assert len(returns) == 3
    assert returns.loc[pd.Timestamp(date(2024, 1, 2))] == pytest.approx(0.10)
    assert returns.loc[pd.Timestamp(date(2024, 1, 3))] == pytest.approx(0.0)
    assert returns.loc[pd.Timestamp(date(2024, 1, 4))] == pytest.approx(-0.05)


def test_time_weighted_return_chain_links_sub_period_returns():
    returns = pd.Series([0.10, 0.0, -0.05])
    twr = time_weighted_return(returns)
    assert twr == pytest.approx(1.10 * 1.00 * 0.95 - 1.0)


def test_time_weighted_return_none_for_empty_series():
    assert time_weighted_return(pd.Series(dtype=float)) is None


def test_annualized_time_weighted_return_matches_exact_one_year_span():
    # 2025 is not a leap year -> exactly 365 days.
    annualized = annualized_time_weighted_return(0.10, date(2025, 1, 1), date(2026, 1, 1))
    assert annualized == pytest.approx(0.10, abs=1e-9)


def test_annualized_time_weighted_return_none_for_zero_day_span():
    assert annualized_time_weighted_return(0.05, date(2025, 1, 1), date(2025, 1, 1)) is None
