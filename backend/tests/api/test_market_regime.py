"""API tests for the Phase 10 Market-Cycle Behaviour endpoints, against
the real Phase 2 seed data (4 illustrative regimes covering 2021-2025)."""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import Scheme

client = TestClient(app)


@pytest.fixture(scope="module")
def bluechip_id() -> int:
    db = SessionLocal()
    try:
        scheme = db.query(Scheme).filter(Scheme.name == "Northbridge Bluechip Equity Fund").first()
        assert scheme is not None, "requires Phase 2 seed data to be loaded"
        return scheme.id
    finally:
        db.close()


def test_list_market_regimes_returns_seeded_regimes():
    response = client.get("/api/market/regimes")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 4
    names = [r["name"] for r in body]
    assert "Sample Regime — Correction" in names
    # sorted by start_date ascending
    start_dates = [r["start_date"] for r in body]
    assert start_dates == sorted(start_dates)


def test_fund_market_regimes_reports_per_regime_behavior(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/market-regimes")
    assert response.status_code == 200
    body = response.json()

    assert len(body["regimes"]) == 4
    assert body["regimes_with_comparison"] == 4
    assert 0 <= body["regimes_outperformed"] <= 4

    for regime in body["regimes"]:
        assert regime["fund_available"] is True
        assert regime["benchmark_available"] is True
        assert regime["excess_return_pct"] == pytest.approx(
            regime["fund_return_pct"] - regime["benchmark_return_pct"], abs=0.01
        )
        assert regime["outperformed"] == (regime["excess_return_pct"] > 0)
        assert isinstance(regime["summary"], str) and len(regime["summary"]) > 0


def test_fund_market_regimes_summary_reflects_outperformance(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/market-regimes")
    body = response.json()
    for regime in body["regimes"]:
        if regime["outperformed"]:
            assert "Outperformed" in regime["summary"]
        else:
            assert "Underperformed" in regime["summary"] or "Matched" in regime["summary"]


def test_market_regimes_methodology_note_present(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/market-regimes")
    body = response.json()
    assert "illustrative" in body["methodology_note"].lower()
    assert "disclaimer" in body


def test_fund_market_regimes_unknown_fund_returns_404():
    response = client.get("/api/funds/999999/market-regimes")
    assert response.status_code == 404
