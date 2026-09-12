import pandas as pd
import pytest

from analytics.drawdown import drawdown_series, max_drawdown


def _series(values):
    dates = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=dates)


def test_drawdown_series_hand_computed():
    nav = _series([100.0, 110.0, 90.0, 95.0, 120.0, 115.0])
    dd = drawdown_series(nav)
    expected = [0.0, 0.0, 90 / 110 - 1, 95 / 110 - 1, 0.0, 115 / 120 - 1]
    assert list(dd) == pytest.approx(expected)


def test_max_drawdown_identifies_peak_trough_and_recovery():
    nav = _series([100.0, 110.0, 90.0, 95.0, 120.0, 115.0])
    result = max_drawdown(nav)

    assert result["max_drawdown_pct"] == pytest.approx(90 / 110 - 1)
    assert result["peak_date"] == nav.index[1]
    assert result["peak_nav"] == pytest.approx(110.0)
    assert result["trough_date"] == nav.index[2]
    assert result["trough_nav"] == pytest.approx(90.0)
    assert result["recovered"] is True
    assert result["recovery_date"] == nav.index[4]
    assert result["recovery_duration_days"] == 2


def test_max_drawdown_not_yet_recovered():
    nav = _series([100.0, 110.0, 90.0, 95.0])
    result = max_drawdown(nav)

    assert result["recovered"] is False
    assert result["recovery_date"] is None
    assert result["recovery_duration_days"] is None


def test_max_drawdown_requires_two_observations():
    with pytest.raises(ValueError):
        max_drawdown(_series([100.0]))
