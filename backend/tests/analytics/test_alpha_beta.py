import pandas as pd
import pytest

from analytics.alpha_beta import annualize_return, beta, jensen_alpha


def test_beta_recovers_exact_linear_coefficient():
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    benchmark = pd.Series([0.01, -0.02, 0.03, 0.00, -0.01], index=dates)
    true_beta = 1.5
    daily_alpha_offset = 0.001
    fund = daily_alpha_offset + true_beta * benchmark  # exact linear relation, no noise

    assert beta(fund, benchmark) == pytest.approx(true_beta)


def test_beta_requires_nonzero_benchmark_variance():
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    benchmark = pd.Series([0.01, 0.01, 0.01], index=dates)
    fund = pd.Series([0.02, 0.015, 0.018], index=dates)
    with pytest.raises(ValueError):
        beta(fund, benchmark)


def test_jensen_alpha_hand_computed():
    result = jensen_alpha(
        fund_annualized_return=0.15,
        benchmark_annualized_return=0.12,
        risk_free_rate_annual=0.06,
        fund_beta=1.2,
    )
    expected = 0.15 - (0.06 + 1.2 * (0.12 - 0.06))
    assert result == pytest.approx(expected)
    assert result == pytest.approx(0.018)


def test_annualize_return_hand_computed():
    returns = pd.Series([0.01, 0.01, 0.01, 0.01])
    expected = (1.01**4) ** (252 / 4) - 1
    assert annualize_return(returns) == pytest.approx(expected)
