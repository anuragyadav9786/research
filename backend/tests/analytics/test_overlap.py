import pytest

from analytics.overlap import overlap_counts, overlap_label, weighted_overlap_pct


def test_weighted_overlap_pct_hand_computed():
    weights_a = {"A": 10.0, "B": 20.0, "C": 5.0}
    weights_b = {"B": 15.0, "C": 10.0, "D": 8.0}
    # min(10,0) + min(20,15) + min(5,10) + min(0,8) = 0 + 15 + 5 + 0 = 20
    assert weighted_overlap_pct(weights_a, weights_b) == pytest.approx(20.0)


def test_weighted_overlap_pct_identical_portfolios_is_full_weight():
    weights = {"A": 40.0, "B": 30.0, "C": 20.0}
    assert weighted_overlap_pct(weights, dict(weights)) == pytest.approx(90.0)


def test_weighted_overlap_pct_disjoint_portfolios_is_zero():
    assert weighted_overlap_pct({"A": 50.0}, {"B": 50.0}) == pytest.approx(0.0)


def test_weighted_overlap_pct_empty_inputs():
    assert weighted_overlap_pct({}, {}) == pytest.approx(0.0)
    assert weighted_overlap_pct({"A": 10.0}, {}) == pytest.approx(0.0)


def test_overlap_counts_hand_computed():
    weights_a = {"A": 10.0, "B": 20.0, "C": 5.0}
    weights_b = {"B": 15.0, "C": 10.0, "D": 8.0}
    result = overlap_counts(weights_a, weights_b)
    assert result == {"common": 2, "only_in_a": 1, "only_in_b": 1}


def test_overlap_label_thresholds():
    assert overlap_label(0) == "low_overlap"
    assert overlap_label(19.99) == "low_overlap"
    assert overlap_label(20) == "moderate_overlap"
    assert overlap_label(49.99) == "moderate_overlap"
    assert overlap_label(50) == "high_overlap"
    assert overlap_label(90) == "high_overlap"
