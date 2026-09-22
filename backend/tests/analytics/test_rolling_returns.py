import pandas as pd
import pytest

from analytics.rolling_returns import (
    benchmark_consistency,
    rolling_return_distribution,
    rolling_returns,
    rolling_window_end_date,
)


def test_rolling_returns_constant_growth_rate_recovers_annual_rate():
    # Daily compounding rate chosen so the series grows at exactly 10%/year;
    # a deterministic construction, so every valid 1-year rolling window
    # should report ~10% with no noise to average away.
    annual_rate = 0.10
    daily_rate = (1 + annual_rate) ** (1 / 365.25) - 1
    n_days = 800
    dates = pd.date_range("2020-01-01", periods=n_days, freq="D")
    nav = pd.Series([100.0 * (1 + daily_rate) ** i for i in range(n_days)], index=dates)

    rolling = rolling_returns(nav, window_years=1.0)

    assert len(rolling) > 400  # most start dates within the first year should have a valid window
    assert rolling.mean() == pytest.approx(annual_rate, abs=1e-6)
    assert rolling.std() < 1e-6  # deterministic series -> ~zero dispersion


def test_rolling_returns_sub_annual_window_uses_simple_not_annualized_return():
    # Same deterministic 10%/year compounding series as the test above.
    # A correct *annualized* 3-month rolling return would still recover
    # ~10% (that's the whole point of annualizing). A *simple* return
    # instead reports the actual quarter's growth: (1.10)**0.25 - 1 ~= 2.4%
    # — an order of magnitude smaller. Asserting the smaller figure proves
    # sub-annual windows use simple_return, not cagr.
    annual_rate = 0.10
    daily_rate = (1 + annual_rate) ** (1 / 365.25) - 1
    n_days = 800
    dates = pd.date_range("2020-01-01", periods=n_days, freq="D")
    nav = pd.Series([100.0 * (1 + daily_rate) ** i for i in range(n_days)], index=dates)

    rolling = rolling_returns(nav, window_years=0.25)

    expected_simple_quarterly_return = (1 + annual_rate) ** 0.25 - 1
    assert not rolling.empty
    assert rolling.mean() == pytest.approx(expected_simple_quarterly_return, abs=1e-4)
    assert rolling.mean() < annual_rate / 2  # sanity check it's nowhere near the annualized rate


def test_rolling_returns_empty_when_history_shorter_than_window():
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    nav = pd.Series([100.0] * 100, index=dates)
    assert rolling_returns(nav, window_years=3.0).empty


def test_rolling_return_distribution_known_values():
    rolling = pd.Series([0.05, 0.10, 0.15, 0.20, 0.25])
    dist = rolling_return_distribution(rolling)
    assert dist["count"] == 5
    assert dist["min"] == pytest.approx(0.05)
    assert dist["max"] == pytest.approx(0.25)
    assert dist["median"] == pytest.approx(0.15)


def test_rolling_return_distribution_empty_series():
    dist = rolling_return_distribution(pd.Series(dtype=float))
    assert dist["count"] == 0
    assert dist["median"] is None


def test_benchmark_consistency_hand_computed():
    idx = pd.date_range("2024-01-01", periods=3, freq="YS")
    fund = pd.Series([0.10, 0.20, 0.05], index=idx)
    benchmark = pd.Series([0.08, 0.08, 0.08], index=idx)

    result = benchmark_consistency(fund, benchmark)

    assert result["aligned_windows"] == 3
    assert result["beat_rate_pct"] == pytest.approx(200 / 3)  # 2 of 3 windows beat benchmark
    assert result["avg_excess_return"] == pytest.approx((0.02 + 0.12 - 0.03) / 3)
    assert result["median_excess_return"] == pytest.approx(0.02)
    assert result["worst_relative_return"] == pytest.approx(-0.03)


def test_benchmark_consistency_no_overlap_returns_none():
    fund = pd.Series([0.1], index=pd.date_range("2024-01-01", periods=1))
    benchmark = pd.Series([0.1], index=pd.date_range("2030-01-01", periods=1))
    result = benchmark_consistency(fund, benchmark)
    assert result["aligned_windows"] == 0
    assert result["beat_rate_pct"] is None


def test_rolling_window_end_date_matches_rolling_returns_own_internal_matching():
    # rolling_returns() indexes each window by its START date only (see its
    # own docstring) — rolling_window_end_date exists to recover the END
    # date for a given start using the exact same asof matching, without
    # duplicating or drifting from that methodology. Verified here by
    # reconstructing each window's actual elapsed days from the recovered
    # end date and confirming it's consistent with the window requested.
    dates = pd.date_range("2020-01-01", periods=800, freq="D")
    nav = pd.Series([100.0 * 1.0003**i for i in range(800)], index=dates)

    rolling = rolling_returns(nav, window_years=0.25)
    assert not rolling.empty

    start_date = rolling.index[10]
    end_date = rolling_window_end_date(nav, start_date, window_years=0.25)

    assert end_date is not None
    elapsed_days = (end_date - start_date).days
    assert 85 <= elapsed_days <= 95  # ~3 months (0.25 * 365.25 ≈ 91 days)


def test_rolling_window_end_date_returns_none_past_available_history():
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    nav = pd.Series([100.0] * 10, index=dates)
    assert rolling_window_end_date(nav, dates[-1], window_years=1.0) is None
