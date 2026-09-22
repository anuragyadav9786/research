import pandas as pd
import pytest

from analytics.investment_value import lumpsum_value, sip_value


def test_lumpsum_value_matches_hand_computed_ratio():
    nav = pd.Series([100.0, 110.0, 121.0], index=pd.date_range("2024-01-01", periods=3, freq="D"))
    # 121/100 = 1.21x growth
    assert lumpsum_value(nav, "2024-01-01", "2024-01-03", 10_000) == pytest.approx(12_100.0)


def test_lumpsum_value_none_when_window_has_fewer_than_two_points():
    nav = pd.Series([100.0], index=pd.date_range("2024-01-01", periods=1))
    assert lumpsum_value(nav, "2024-01-01", "2025-01-01", 10_000) is None


def test_sip_value_daily_uses_every_trading_day():
    # 5 trading days, NAV flat at 100 except the last day doubles: buying
    # 1 unit's worth (100/100=1 unit) on 4 days + 100/200=0.5 unit on the
    # 5th, then all units valued at the final NAV of 200.
    nav = pd.Series([100.0, 100.0, 100.0, 100.0, 200.0], index=pd.date_range("2024-01-01", periods=5, freq="D"))
    result = sip_value(nav, "2024-01-01", "2024-01-05", 100.0, "daily")
    assert result is not None
    assert result["installments"] == 5
    assert result["invested_amount"] == pytest.approx(500.0)
    total_units = 4 * (100 / 100) + (100 / 200)
    assert result["value"] == pytest.approx(total_units * 200.0)


def test_sip_value_weekly_skips_non_trading_days_via_asof():
    # Daily NAV for 3 weeks; weekly SIP should land on day 0, 7, 14 and
    # buy at whatever NAV is available on/before each of those dates.
    dates = pd.date_range("2024-01-01", periods=21, freq="D")
    nav = pd.Series([100.0 + i for i in range(21)], index=dates)
    result = sip_value(nav, dates[0], dates[-1], 1000.0, "weekly")
    assert result is not None
    assert result["installments"] == 3
    assert result["invested_amount"] == pytest.approx(3000.0)


def test_sip_value_monthly_cadence():
    dates = pd.date_range("2024-01-01", periods=95, freq="D")  # Jan 1 - Apr 4 2024
    nav = pd.Series([100.0] * len(dates), index=dates)
    result = sip_value(nav, dates[0], dates[-1], 500.0, "monthly")
    assert result is not None
    assert result["installments"] == 4  # Jan 1, Feb 1, Mar 1, Apr 1 (94 days later, within range)
    assert result["value"] == pytest.approx(2000.0)  # flat NAV: value == invested


def test_sip_value_none_for_empty_window():
    nav = pd.Series([100.0], index=pd.date_range("2024-01-01", periods=1))
    assert sip_value(nav, "2025-01-01", "2025-06-01", 1000.0, "monthly") is None


def test_sip_value_none_for_unknown_frequency():
    nav = pd.Series([100.0, 110.0], index=pd.date_range("2024-01-01", periods=2))
    assert sip_value(nav, "2024-01-01", "2024-01-02", 1000.0, "fortnightly") is None
