import pandas as pd
import pytest

from analytics.correlation import return_correlation


def _series(values, start="2024-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


def test_perfectly_positively_correlated_series():
    a = _series([0.01, -0.02, 0.03, 0.00, -0.01])
    b = 2 * a  # exact linear relationship, positive slope
    assert return_correlation(a, b) == pytest.approx(1.0)


def test_perfectly_negatively_correlated_series():
    a = _series([0.01, -0.02, 0.03, 0.00, -0.01])
    b = -1 * a
    assert return_correlation(a, b) == pytest.approx(-1.0)


def test_zero_variance_series_returns_none():
    a = _series([0.01, -0.02, 0.03])
    constant = _series([0.005, 0.005, 0.005])
    assert return_correlation(a, constant) is None


def test_insufficient_overlap_returns_none():
    a = pd.Series([0.01], index=pd.date_range("2024-01-01", periods=1))
    b = pd.Series([0.01], index=pd.date_range("2030-01-01", periods=1))
    assert return_correlation(a, b) is None


def test_aligns_on_common_dates_only():
    a = _series([0.01, 0.02, 0.03, 0.04], start="2024-01-01")
    b = _series([0.01, 0.02, 0.03, 0.04], start="2024-01-02")  # shifted by 1 day
    # Only 3 overlapping dates (2024-01-02..04), identical values -> perfect correlation
    assert return_correlation(a, b) == pytest.approx(1.0)
