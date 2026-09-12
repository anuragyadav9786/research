import pandas as pd
import pytest

from analytics.market_regime import regime_metrics


def _series(values, start="2024-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


def test_regime_metrics_hand_computed_return_and_drawdown():
    nav = _series([100.0, 110.0, 90.0, 95.0, 105.0])
    result = regime_metrics(nav, "2024-01-01", "2024-01-05")

    assert result["available"] is True
    assert result["observations"] == 5
    # simple return: 105/100 - 1 = 0.05 -> 5%
    assert result["return_pct"] == pytest.approx(5.0)
    # max drawdown: 90/110 - 1 = -0.181818... -> -18.1818%
    assert result["max_drawdown_pct"] == pytest.approx((90 / 110 - 1) * 100)
    assert result["volatility_pct"] is not None


def test_regime_metrics_restricts_to_window():
    nav = _series([100.0, 200.0, 100.0, 50.0, 300.0])  # wild swings outside the window
    # only look at the middle 3 points: index 1..3 -> dates day2..day4
    result = regime_metrics(nav, nav.index[1], nav.index[3])
    assert result["observations"] == 3
    # return over that sub-window: 50/200 - 1 = -0.75 -> -75%
    assert result["return_pct"] == pytest.approx(-75.0)


def test_regime_metrics_insufficient_observations_returns_unavailable():
    nav = _series([100.0], start="2024-06-01")
    result = regime_metrics(nav, "2024-01-01", "2024-12-31")
    assert result["available"] is False
    assert result["observations"] == 1
    assert result["return_pct"] is None
    assert result["volatility_pct"] is None
    assert result["max_drawdown_pct"] is None


def test_regime_metrics_no_overlap_with_window_returns_unavailable():
    nav = _series([100.0, 101.0, 102.0], start="2020-01-01")
    result = regime_metrics(nav, "2024-01-01", "2024-12-31")
    assert result["available"] is False
    assert result["observations"] == 0


def test_regime_metrics_flat_series_has_zero_return_and_drawdown():
    nav = _series([100.0, 100.0, 100.0])
    result = regime_metrics(nav, nav.index[0], nav.index[-1])
    assert result["return_pct"] == pytest.approx(0.0)
    assert result["max_drawdown_pct"] == pytest.approx(0.0)
    assert result["volatility_pct"] == pytest.approx(0.0)
