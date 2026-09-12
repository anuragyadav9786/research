"""API tests for the Phase 7 portfolio/holdings endpoint, against the real
Phase 2 seed data (same pattern as tests/api/test_funds.py)."""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import Scheme

client = TestClient(app)


@pytest.fixture(scope="module")
def bluechip_fund_id() -> int:
    db = SessionLocal()
    try:
        scheme = db.query(Scheme).filter(Scheme.name == "Northbridge Bluechip Equity Fund").first()
        assert scheme is not None, "requires Phase 2 seed data to be loaded"
        return scheme.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def debt_fund_id() -> int:
    db = SessionLocal()
    try:
        scheme = db.query(Scheme).filter(Scheme.name == "Meridian Short Duration Debt Fund").first()
        assert scheme is not None, "requires Phase 2 seed data to be loaded"
        return scheme.id
    finally:
        db.close()


def test_portfolio_reports_top_holdings_and_concentration(bluechip_fund_id):
    response = client.get(f"/api/funds/{bluechip_fund_id}/portfolio")
    assert response.status_code == 200
    body = response.json()

    assert body["available"] is True
    assert body["total_holdings"] == 8
    assert body["top_holdings"][0]["security_name"] == "Sample Bank Corp Ltd"
    assert body["top_holdings"][0]["rank"] == 1
    # ranks strictly increasing, weights non-increasing
    weights = [h["weight_pct"] for h in body["top_holdings"]]
    assert weights == sorted(weights, reverse=True)
    assert body["top5_weight_pct"] == pytest.approx(37.8)
    assert body["top10_weight_pct"] == pytest.approx(51.9)  # only 8 holdings exist
    assert body["hhi"] == pytest.approx(362.59, abs=0.01)
    assert body["hhi_label"] == "diversified"


def test_portfolio_sector_and_market_cap_allocation_sum_to_disclosed_weight(bluechip_fund_id):
    response = client.get(f"/api/funds/{bluechip_fund_id}/portfolio")
    body = response.json()

    sector_total = sum(s["weight_pct"] for s in body["sector_allocation"])
    market_cap_total = sum(s["weight_pct"] for s in body["market_cap_allocation"])
    assert sector_total == pytest.approx(body["total_disclosed_weight_pct"])
    assert market_cap_total == pytest.approx(body["total_disclosed_weight_pct"])
    # allocation lists are sorted descending by weight
    sector_weights = [s["weight_pct"] for s in body["sector_allocation"]]
    assert sector_weights == sorted(sector_weights, reverse=True)


def test_portfolio_handles_unclassified_bonds(debt_fund_id):
    response = client.get(f"/api/funds/{debt_fund_id}/portfolio")
    assert response.status_code == 200
    body = response.json()

    assert body["available"] is True
    assert all(h["sector"] is None and h["market_cap_category"] is None for h in body["top_holdings"])
    assert body["sector_allocation"] == [{"label": "unclassified", "weight_pct": body["total_disclosed_weight_pct"]}]
    assert body["hhi_label"] == "high_concentration"


def test_portfolio_provenance_fields_present(bluechip_fund_id):
    response = client.get(f"/api/funds/{bluechip_fund_id}/portfolio")
    body = response.json()
    assert body["as_of_date"] is not None
    assert body["source_name"] == "Synthetic Sample Data Generator"


def test_portfolio_unknown_fund_returns_404():
    response = client.get("/api/funds/999999/portfolio")
    assert response.status_code == 404
