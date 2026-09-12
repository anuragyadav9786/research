import pytest

from analytics.stress_testing import SCENARIOS, exposure_shock_impact_pct, index_shock_impact_pct


def test_index_shock_impact_hand_computed():
    # beta 1.2, market falls 25% -> -30%
    assert index_shock_impact_pct(1.2, -25.0) == pytest.approx(-30.0)


def test_index_shock_impact_beta_below_one_dampens():
    assert index_shock_impact_pct(0.5, -25.0) == pytest.approx(-12.5)


def test_index_shock_impact_negative_beta_inverts():
    assert index_shock_impact_pct(-0.5, -25.0) == pytest.approx(12.5)


def test_index_shock_impact_zero_beta_is_zero():
    assert index_shock_impact_pct(0.0, -25.0) == pytest.approx(0.0)


def test_exposure_shock_impact_hand_computed():
    # 40% mid-cap exposure, midcaps fall 40% -> -16%
    assert exposure_shock_impact_pct(40.0, -40.0) == pytest.approx(-16.0)


def test_exposure_shock_impact_zero_exposure_is_zero():
    assert exposure_shock_impact_pct(0.0, -30.0) == pytest.approx(0.0)


def test_exposure_shock_impact_full_exposure_equals_shock():
    assert exposure_shock_impact_pct(100.0, -30.0) == pytest.approx(-30.0)


def test_scenarios_table_covers_all_seven_spec_scenarios():
    assert len(SCENARIOS) == 7
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids))  # no duplicate scenario ids


def test_scenarios_table_shock_types_are_valid():
    valid_types = {"index", "sector", "market_cap", "unmodeled"}
    for scenario in SCENARIOS:
        assert scenario["shock_type"] in valid_types


def test_unmodeled_scenarios_carry_a_reason():
    for scenario in SCENARIOS:
        if scenario["shock_type"] == "unmodeled":
            assert scenario.get("reason"), f"{scenario['id']} must document why it's unmodeled"


def test_modeled_scenarios_carry_a_shock_pct():
    for scenario in SCENARIOS:
        if scenario["shock_type"] in ("index", "sector", "market_cap"):
            assert isinstance(scenario.get("shock_pct"), (int, float))


def test_macro_scenarios_from_spec_are_explicitly_unmodeled():
    unmodeled_ids = {s["id"] for s in SCENARIOS if s["shock_type"] == "unmodeled"}
    assert unmodeled_ids == {"rates_up_sharply", "recession", "inr_depreciation", "inflation_shock"}
