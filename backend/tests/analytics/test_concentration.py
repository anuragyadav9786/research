import pytest

from analytics.concentration import group_weights, herfindahl_hirschman_index, hhi_label, top_n_weight_pct


def test_group_weights_sums_by_label():
    items = [("IT", 10.0), ("Financials", 15.0), ("IT", 5.0), ("Energy", 8.0)]
    result = group_weights(items)
    assert result == {"IT": 15.0, "Financials": 15.0, "Energy": 8.0}


def test_group_weights_empty_input():
    assert group_weights([]) == {}


def test_top_n_weight_pct_hand_computed():
    weights = [5.0, 20.0, 8.0, 15.0, 2.0]
    # sorted desc: 20, 15, 8, 5, 2 -> top 3 = 20+15+8 = 43
    assert top_n_weight_pct(weights, 3) == pytest.approx(43.0)


def test_top_n_weight_pct_fewer_holdings_than_n_sums_all():
    weights = [10.0, 20.0]
    assert top_n_weight_pct(weights, 10) == pytest.approx(30.0)


def test_top_n_weight_pct_rejects_non_positive_n():
    with pytest.raises(ValueError):
        top_n_weight_pct([1.0, 2.0], 0)


def test_hhi_equal_weight_20_holdings():
    # 20 equal-weight holdings of 5% each -> HHI = 20 * (5/100)^2 * 10000 = 500
    weights = [5.0] * 20
    assert herfindahl_hirschman_index(weights) == pytest.approx(500.0)


def test_hhi_single_holding_is_max():
    # One 100% holding -> HHI = (100/100)^2 * 10000 = 10000
    assert herfindahl_hirschman_index([100.0]) == pytest.approx(10000.0)


def test_hhi_hand_computed_mixed_weights():
    weights = [40.0, 30.0, 20.0, 10.0]
    # (0.4^2 + 0.3^2 + 0.2^2 + 0.1^2) * 10000 = (0.16+0.09+0.04+0.01)*10000 = 3000
    assert herfindahl_hirschman_index(weights) == pytest.approx(3000.0)


def test_hhi_label_thresholds():
    assert hhi_label(1000) == "diversified"
    assert hhi_label(1499.99) == "diversified"
    assert hhi_label(1500) == "moderate_concentration"
    assert hhi_label(2499.99) == "moderate_concentration"
    assert hhi_label(2500) == "high_concentration"
    assert hhi_label(5000) == "high_concentration"
