"""API tests for the Phase 9 multi-fund Portfolio Analysis endpoint,
against the real Phase 2 seed data."""
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
def flexicap_id() -> int:
    return _scheme_id("Northbridge Flexi Cap Fund")


@pytest.fixture(scope="module")
def midcap_id() -> int:
    return _scheme_id("Meridian Midcap Opportunities Fund")


def test_analyse_combines_three_funds(bluechip_id, flexicap_id, midcap_id):
    response = client.post(
        "/api/portfolio/analyse",
        json={"holdings": [
            {"fund_id": bluechip_id, "weight_pct": 50},
            {"fund_id": flexicap_id, "weight_pct": 30},
            {"fund_id": midcap_id, "weight_pct": 20},
        ]},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["total_weight_pct"] == pytest.approx(100.0)
    assert len(body["funds"]) == 3

    # Sample Bank Corp Ltd: 9.8% in bluechip, 6.1% in flexicap, absent from midcap
    # effective = 0.5*9.8 + 0.3*6.1 = 4.9 + 1.83 = 6.73
    bank_corp = next(h for h in body["combined_top_holdings"] if h["security_name"] == "Sample Bank Corp Ltd")
    assert bank_corp["effective_weight_pct"] == pytest.approx(6.73)
    assert bank_corp["rank"] == 1

    assert body["concentration"]["hhi_label"] == "diversified"
    assert len(body["pairwise_overlap"]) == 3  # 3 funds -> 3 unique pairs
    assert body["risk"]["available"] is True
    assert body["risk"]["observations_used"] > 1000
    assert body["drawdown"]["available"] is True
    assert body["average_pairwise_correlation"] is not None


def test_analyse_holdings_sum_must_be_near_100(bluechip_id, flexicap_id):
    response = client.post(
        "/api/portfolio/analyse",
        json={"holdings": [
            {"fund_id": bluechip_id, "weight_pct": 50},
            {"fund_id": flexicap_id, "weight_pct": 30},
        ]},
    )
    assert response.status_code == 400
    assert "80.00%" in response.json()["detail"]


def test_analyse_rejects_duplicate_fund_id(bluechip_id):
    response = client.post(
        "/api/portfolio/analyse",
        json={"holdings": [
            {"fund_id": bluechip_id, "weight_pct": 50},
            {"fund_id": bluechip_id, "weight_pct": 50},
        ]},
    )
    assert response.status_code == 400


def test_analyse_unknown_fund_returns_404(bluechip_id):
    response = client.post(
        "/api/portfolio/analyse",
        json={"holdings": [
            {"fund_id": bluechip_id, "weight_pct": 50},
            {"fund_id": 999999, "weight_pct": 50},
        ]},
    )
    assert response.status_code == 404


def test_analyse_requires_at_least_two_holdings(bluechip_id):
    response = client.post(
        "/api/portfolio/analyse",
        json={"holdings": [{"fund_id": bluechip_id, "weight_pct": 100}]},
    )
    assert response.status_code == 422


def test_analyse_allocation_sums_reconcile(bluechip_id, flexicap_id):
    response = client.post(
        "/api/portfolio/analyse",
        json={"holdings": [
            {"fund_id": bluechip_id, "weight_pct": 60},
            {"fund_id": flexicap_id, "weight_pct": 40},
        ]},
    )
    body = response.json()
    sector_total = sum(s["weight_pct"] for s in body["sector_allocation"])
    market_cap_total = sum(s["weight_pct"] for s in body["market_cap_allocation"])
    assert sector_total == pytest.approx(market_cap_total, abs=0.01)
