import pandas as pd
import pytest

from analytics.capture_ratio import downside_capture, upside_capture


def test_upside_and_downside_capture_hand_computed():
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    benchmark = pd.Series([0.05, -0.03, 0.02, -0.01, 0.04], index=dates)
    fund = pd.Series([0.06, -0.02, 0.01, -0.015, 0.05], index=dates)

    # Upside periods: indices 0, 2, 4 (benchmark > 0)
    bench_up_compound = (1.05 * 1.02 * 1.04) - 1
    fund_up_compound = (1.06 * 1.01 * 1.05) - 1
    expected_upside = (fund_up_compound / bench_up_compound) * 100

    # Downside periods: indices 1, 3 (benchmark < 0)
    bench_down_compound = (0.97 * 0.99) - 1
    fund_down_compound = (0.98 * 0.985) - 1
    expected_downside = (fund_down_compound / bench_down_compound) * 100

    assert upside_capture(fund, benchmark) == pytest.approx(expected_upside)
    assert downside_capture(fund, benchmark) == pytest.approx(expected_downside)


def test_capture_ratio_none_when_no_matching_periods():
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    benchmark = pd.Series([0.01, 0.02, 0.03], index=dates)  # never negative
    fund = pd.Series([0.01, 0.02, 0.03], index=dates)
    assert downside_capture(fund, benchmark) is None
