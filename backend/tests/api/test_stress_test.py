"""API tests for the Phase 11 Stress-Test Engine, against the real
Phase 2 seed data."""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import Scheme

client = TestClient(app)


def _scheme_id(name: str) -> int:
    db = SessionLocal()
    try:
        scheme = db.query(Scheme).filter(Scheme.name == name).first()
        assert scheme is not None, "requires Phase 2 seed data to be loaded"
        return scheme.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def bluechip_id() -> int:
    return _scheme_id("Northbridge Bluechip Equity Fund")


@pytest.fixture(scope="module")
def debt_fund_id() -> int:
    return _scheme_id("Meridian Short Duration Debt Fund")


def test_stress_test_covers_all_seven_scenarios(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/stress-test")
    assert response.status_code == 200
    body = response.json()
    assert len(body["scenarios"]) == 7
    assert body["fund_beta"] is not None


def test_stress_test_index_shock_matches_beta_times_shock(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/stress-test")
    body = response.json()
    market_scenario = next(s for s in body["scenarios"] if s["scenario_id"] == "broad_market_down_25")
    assert market_scenario["available"] is True
    assert market_scenario["estimated_impact_pct"] == pytest.approx(body["fund_beta"] * -25.0, abs=0.01)


def test_stress_test_exposure_shocks_match_disclosed_allocation(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/stress-test")
    body = response.json()

    midcap = next(s for s in body["scenarios"] if s["scenario_id"] == "midcap_down_40")
    assert midcap["available"] is True
    assert midcap["estimated_impact_pct"] == pytest.approx((midcap["exposure_pct"] / 100) * -40.0, abs=0.01)

    it_sector = next(s for s in body["scenarios"] if s["scenario_id"] == "it_sector_down_30")
    assert it_sector["available"] is True
    assert it_sector["exposure_pct"] > 0  # Bluechip has disclosed IT holdings
    assert it_sector["estimated_impact_pct"] == pytest.approx((it_sector["exposure_pct"] / 100) * -30.0, abs=0.01)


def test_stress_test_macro_scenarios_are_explicitly_unavailable(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/stress-test")
    body = response.json()
    unmodeled_ids = {"rates_up_sharply", "recession", "inr_depreciation", "inflation_shock"}
    for scenario in body["scenarios"]:
        if scenario["scenario_id"] in unmodeled_ids:
            assert scenario["available"] is False
            assert scenario["estimated_impact_pct"] is None
            assert scenario["reason"] is not None and len(scenario["reason"]) > 0


def test_stress_test_debt_fund_has_zero_equity_sector_exposure(debt_fund_id):
    response = client.get(f"/api/funds/{debt_fund_id}/stress-test")
    assert response.status_code == 200
    body = response.json()
    it_sector = next(s for s in body["scenarios"] if s["scenario_id"] == "it_sector_down_30")
    assert it_sector["available"] is True
    assert it_sector["exposure_pct"] == pytest.approx(0.0)
    assert it_sector["estimated_impact_pct"] == pytest.approx(0.0)


def test_stress_test_hypothetical_notice_present(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/stress-test")
    body = response.json()
    assert "hypothetical" in body["hypothetical_notice"].lower()
    assert "disclaimer" in body


def test_stress_test_unknown_fund_returns_404():
    response = client.get("/api/funds/999999/stress-test")
    assert response.status_code == 404
