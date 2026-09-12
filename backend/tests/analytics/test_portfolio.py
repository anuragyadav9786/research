import pandas as pd
import pytest

from analytics.portfolio import combine_effective_weights, combine_weighted_returns, synthetic_nav_from_returns


def test_combine_effective_weights_hand_computed():
    per_fund_weights = {
        "fund_a": {"Sec1": 40.0, "Sec2": 20.0},
        "fund_b": {"Sec2": 30.0, "Sec3": 50.0},
    }
    fund_weights_pct = {"fund_a": 60.0, "fund_b": 40.0}
    # Sec1: 0.6 * 40 = 24
    # Sec2: 0.6 * 20 + 0.4 * 30 = 12 + 12 = 24
    # Sec3: 0.4 * 50 = 20
    result = combine_effective_weights(per_fund_weights, fund_weights_pct)
    assert result == pytest.approx({"Sec1": 24.0, "Sec2": 24.0, "Sec3": 20.0})


def test_combine_effective_weights_single_fund_is_scaled_by_its_portfolio_weight():
    per_fund_weights = {"fund_a": {"Sec1": 50.0}}
    fund_weights_pct = {"fund_a": 70.0}
    result = combine_effective_weights(per_fund_weights, fund_weights_pct)
    assert result == pytest.approx({"Sec1": 35.0})


def test_combine_effective_weights_empty_inputs():
    assert combine_effective_weights({}, {}) == {}


def _series(values, start="2024-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


def test_combine_weighted_returns_hand_computed():
    returns_a = _series([0.02, -0.01, 0.03])
    returns_b = _series([0.00, 0.04, -0.02])
    fund_weights_pct = {"a": 60.0, "b": 40.0}
    result = combine_weighted_returns({"a": returns_a, "b": returns_b}, fund_weights_pct)
    # day0: 0.6*0.02 + 0.4*0.00 = 0.012
    # day1: 0.6*-0.01 + 0.4*0.04 = -0.006 + 0.016 = 0.010
    # day2: 0.6*0.03 + 0.4*-0.02 = 0.018 - 0.008 = 0.010
    expected = [0.012, 0.010, 0.010]
    assert list(result.round(10)) == pytest.approx(expected)


def test_combine_weighted_returns_uses_only_common_dates():
    returns_a = _series([0.01, 0.02, 0.03], start="2024-01-01")
    returns_b = _series([0.01, 0.02], start="2024-01-02")  # starts 1 day later, shorter
    result = combine_weighted_returns({"a": returns_a, "b": returns_b}, {"a": 50.0, "b": 50.0})
    assert len(result) == 2  # only 2024-01-02 and 2024-01-03 are common


def test_combine_weighted_returns_raises_on_no_common_dates():
    returns_a = _series([0.01], start="2024-01-01")
    returns_b = _series([0.01], start="2030-01-01")
    with pytest.raises(ValueError):
        combine_weighted_returns({"a": returns_a, "b": returns_b}, {"a": 50.0, "b": 50.0})


def test_combine_weighted_returns_raises_on_empty_input():
    with pytest.raises(ValueError):
        combine_weighted_returns({}, {})


def test_synthetic_nav_from_returns_hand_computed():
    returns = _series([0.10, -0.10, 0.05])
    nav = synthetic_nav_from_returns(returns, base=100.0)
    # 100 * 1.10 = 110; 110 * 0.90 = 99; 99 * 1.05 = 103.95
    assert list(nav.round(6)) == pytest.approx([110.0, 99.0, 103.95])


def test_synthetic_nav_from_returns_default_base():
    returns = _series([0.0, 0.0])
    nav = synthetic_nav_from_returns(returns)
    assert list(nav) == pytest.approx([100.0, 100.0])
