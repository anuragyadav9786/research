"""API tests for the Phase 5 fund research endpoints, run against the real
local Postgres database with Phase 2 seed data loaded (same pattern as
tests/api/test_health.py). These are read-only against existing seed
data — no cleanup needed."""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import Scheme

client = TestClient(app)


@pytest.fixture(scope="module")
def seeded_fund_id() -> int:
    db = SessionLocal()
    try:
        scheme = db.query(Scheme).filter(Scheme.name == "Northbridge Bluechip Equity Fund").first()
        assert scheme is not None, "requires Phase 2 seed data to be loaded"
        return scheme.id
    finally:
        db.close()


def test_list_funds_returns_seeded_schemes():
    response = client.get("/api/funds")
    assert response.status_code == 200
    names = [f["scheme_name"] for f in response.json()]
    assert "Northbridge Bluechip Equity Fund" in names


def test_list_funds_search_filter():
    response = client.get("/api/funds", params={"search": "Midcap"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["scheme_name"] == "Meridian Midcap Opportunities Fund"


def test_list_funds_search_no_match_returns_empty_list():
    response = client.get("/api/funds", params={"search": "NoSuchFundNameXYZ"})
    assert response.status_code == 200
    assert response.json() == []


def test_get_fund_detail_includes_both_variants(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["scheme_name"] == "Northbridge Bluechip Equity Fund"
    plans = {v["plan"] for v in body["variants"]}
    assert plans == {"direct", "regular"}
    for variant in body["variants"]:
        assert variant["latest_nav"] is not None
        assert variant["latest_nav_date"] is not None


def test_get_fund_nav_history_returns_ordered_series(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/nav-history")
    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_name"] == "Nifty 50 TRI (Sample Series)"
    assert len(body["fund_points"]) > 1000
    assert len(body["benchmark_points"]) > 1000
    dates = [p["date"] for p in body["fund_points"]]
    assert dates == sorted(dates)
    assert all(p["value"] > 0 for p in body["fund_points"])


def test_get_fund_returns_reports_all_windows(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/returns")
    assert response.status_code == 200
    body = response.json()
    assert set(body["windows"].keys()) == {"1y", "3y", "5y", "7y", "10y"}
    # ~4 years of seed history -> 1y and 3y available, 5y/7y/10y not
    assert body["windows"]["1y"]["available"] is True
    assert body["windows"]["10y"]["available"] is False
    assert body["windows"]["10y"]["reason"] == "insufficient_history"
    assert "disclaimer" in body


def test_get_fund_risk_reports_metrics(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/risk")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["observations_used"] > 1000
    assert isinstance(body["volatility_pct"], float)
    assert body["risk_free_rate_pct"] == pytest.approx(7.0)


def test_get_fund_rolling_returns_reports_percentages(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/rolling-returns", params={"window_years": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["distribution"]["count"] > 0
    # values should look like percentages (tens), not raw fractions (<1)
    assert abs(body["distribution"]["median"]) < 100
    assert body["benchmark_consistency"]["aligned_windows"] > 0


def test_get_fund_rolling_returns_insufficient_window(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/rolling-returns", params={"window_years": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] == "insufficient_history"
    assert body["distribution"]["count"] == 0


def test_get_fund_drawdown_reports_episode(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/drawdown")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["max_drawdown_pct"] < 0
    assert body["peak_date"] is not None
    assert body["trough_date"] is not None


def test_get_fund_intelligence_bundles_everything(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/intelligence")
    assert response.status_code == 200
    body = response.json()
    assert body["fund"]["id"] == seeded_fund_id
    assert body["variant"]["plan"] == "direct"  # default plan
    assert "windows" in body["returns"]
    assert body["risk"]["available"] is True
    assert body["drawdown"]["available"] is True


def test_unknown_fund_returns_404():
    response = client.get("/api/funds/999999")
    assert response.status_code == 404


def test_unknown_variant_returns_404(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/returns", params={"option": "idcw"})
    assert response.status_code == 404


def test_invalid_plan_query_param_returns_422(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/returns", params={"plan": "not-a-real-plan"})
    assert response.status_code == 422
