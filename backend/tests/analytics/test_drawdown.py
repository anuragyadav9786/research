import pandas as pd
import pytest

from analytics.drawdown import drawdown_episodes, drawdown_series, max_drawdown


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


def test_drawdown_episodes_finds_both_distinct_episodes_most_severe_first():
    nav = _series([100.0, 110.0, 90.0, 95.0, 120.0, 115.0])
    episodes = drawdown_episodes(nav)

    assert len(episodes) == 2
    first, second = episodes
    assert first["peak_date"] == nav.index[1]
    assert first["trough_date"] == nav.index[2]
    assert first["recovered"] is True
    assert first["recovery_date"] == nav.index[4]

    assert second["peak_date"] == nav.index[4]
    assert second["trough_date"] == nav.index[5]
    assert second["recovered"] is False
    assert second["recovery_date"] is None

    assert first["max_drawdown_pct"] < second["max_drawdown_pct"]  # worst (most negative) first


def test_drawdown_episodes_first_result_matches_max_drawdown():
    nav = _series([100.0, 110.0, 90.0, 95.0, 120.0, 115.0])
    assert drawdown_episodes(nav)[0] == max_drawdown(nav)


def test_drawdown_episodes_filters_out_shallow_noise():
    # A tiny 0.5% dip between two deeper episodes should be dropped by the default 1% materiality threshold.
    nav = _series([100.0, 110.0, 90.0, 120.0, 119.4, 130.0, 100.0])
    episodes = drawdown_episodes(nav)
    assert all(abs(e["max_drawdown_pct"]) * 100 >= 1.0 for e in episodes)
    assert len(episodes) == 2  # the 110->90 episode and the 130->100 (unrecovered) episode only


def test_drawdown_episodes_requires_two_observations():
    with pytest.raises(ValueError):
        drawdown_episodes(_series([100.0]))


def test_drawdown_episodes_empty_when_series_never_declines():
    nav = _series([100.0, 110.0, 120.0, 130.0])
    assert drawdown_episodes(nav) == []
