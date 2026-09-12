import math
import statistics

import pandas as pd
import pytest

from analytics.risk import (
    annualized_volatility,
    downside_deviation,
    sharpe_ratio,
    sortino_ratio,
)


def test_annualized_volatility_matches_independent_stdev_calculation():
    values = [0.01, -0.01, 0.02, -0.02, 0.005]
    returns = pd.Series(values)
    # Independent reference computation using Python's stdlib `statistics`
    # module (sample stdev, ddof=1) rather than re-deriving the analytics
    # module's own formula.
    expected = statistics.stdev(values) * math.sqrt(252)
    assert annualized_volatility(returns) == pytest.approx(expected)


def test_annualized_volatility_requires_two_observations():
    with pytest.raises(ValueError):
        annualized_volatility(pd.Series([0.01]))


def test_downside_deviation_hand_computed():
    returns = pd.Series([-0.02, 0.01, -0.01, 0.03])
    # downside vs target=0: [-0.02, 0, -0.01, 0] -> squared mean = 0.0005/4? see below
    # squares: 0.0004, 0, 0.0001, 0 -> mean = 0.000125 -> sqrt = 0.0111803398875
    expected = math.sqrt(0.000125) * math.sqrt(252)
    assert downside_deviation(returns) == pytest.approx(expected)


def test_sharpe_ratio_hand_computed():
    values = [0.001, 0.002, 0.0015, 0.0025, 0.0018]
    returns = pd.Series(values)
    risk_free_annual = 0.07
    daily_rf = (1 + risk_free_annual) ** (1 / 252) - 1
    excess = [v - daily_rf for v in values]
    expected = (statistics.mean(excess) / statistics.stdev(values)) * math.sqrt(252)
    assert sharpe_ratio(returns, risk_free_annual) == pytest.approx(expected)


def test_sharpe_ratio_zero_volatility_raises():
    returns = pd.Series([0.001, 0.001, 0.001])
    with pytest.raises(ValueError):
        sharpe_ratio(returns, 0.07)


def test_sortino_ratio_zero_downside_deviation_raises():
    # every return above the risk-free target -> no downside observations
    returns = pd.Series([0.01, 0.02, 0.015, 0.03])
    with pytest.raises(ValueError):
        sortino_ratio(returns, risk_free_rate_annual=0.0)


def test_sortino_ratio_hand_computed():
    values = [0.005, -0.01, 0.02, -0.02, 0.01]
    returns = pd.Series(values)
    risk_free_annual = 0.05
    daily_rf = (1 + risk_free_annual) ** (1 / 252) - 1
    downside_sq = [min(v - daily_rf, 0.0) ** 2 for v in values]
    dd = math.sqrt(statistics.mean(downside_sq)) * math.sqrt(252)
    annualized_excess = (statistics.mean(values) - daily_rf) * 252
    expected = annualized_excess / dd
    assert sortino_ratio(returns, risk_free_annual) == pytest.approx(expected)
