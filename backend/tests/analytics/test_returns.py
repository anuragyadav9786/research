import pandas as pd
import pytest

from analytics.returns import cagr, cagr_for_window, returns_series, simple_return


def test_simple_return():
    assert simple_return(100, 110) == pytest.approx(0.10)
    assert simple_return(100, 90) == pytest.approx(-0.10)


def test_simple_return_rejects_non_positive_start():
    with pytest.raises(ValueError):
        simple_return(0, 100)


def test_cagr_known_value():
    # 100 -> 200 over 5 years: 2^(1/5) - 1
    assert cagr(100, 200, 5) == pytest.approx(0.1486983549970351, rel=1e-9)


def test_cagr_flat_is_zero():
    assert cagr(100, 100, 3) == pytest.approx(0.0)


def test_cagr_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        cagr(-10, 100, 5)
    with pytest.raises(ValueError):
        cagr(100, 200, 0)


def test_returns_series_matches_hand_computed_pct_change():
    nav = pd.Series([100.0, 110.0, 121.0], index=pd.date_range("2024-01-01", periods=3))
    result = returns_series(nav)
    assert list(result.round(10)) == [pytest.approx(0.10), pytest.approx(0.10)]


def test_returns_series_empty_input():
    assert returns_series(pd.Series(dtype=float)).empty


def test_cagr_for_window_none_when_insufficient_data():
    nav = pd.Series([100.0], index=pd.date_range("2024-01-01", periods=1))
    assert cagr_for_window(nav, "2024-01-01", "2025-01-01") is None
