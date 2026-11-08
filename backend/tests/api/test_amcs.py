"""API tests for the AMC browsing endpoints, run against the real local
Postgres database with Phase 2 seed data loaded (same pattern as
tests/api/test_funds.py). Read-only against existing seed data.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import AMC, FundFamily, Scheme

client = TestClient(app)


@pytest.fixture(scope="module")
def seeded_amc_id() -> int:
    db = SessionLocal()
    try:
        scheme = db.query(Scheme).filter(Scheme.name == "Northbridge Bluechip Equity Fund").first()
        assert scheme is not None, "requires Phase 2 seed data to be loaded"
        family = db.get(FundFamily, scheme.fund_family_id)
        return family.amc_id
    finally:
        db.close()


def test_list_amcs_returns_seeded_amc(seeded_amc_id):
    response = client.get("/api/amcs")
    assert response.status_code == 200
    body = response.json()
    ids = [a["id"] for a in body["items"]]
    assert seeded_amc_id in ids


def test_list_amcs_counts_are_non_negative_integers():
    response = client.get("/api/amcs")
    assert response.status_code == 200
    for amc in response.json()["items"]:
        assert amc["fund_family_count"] >= 0
        assert amc["scheme_count"] >= 0
        assert amc["schemes_with_holdings_count"] >= 0
        assert amc["schemes_with_holdings_count"] <= amc["scheme_count"]


def test_get_amc_detail_lists_its_schemes(seeded_amc_id):
    response = client.get(f"/api/amcs/{seeded_amc_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == seeded_amc_id
    names = [s["scheme_name"] for s in body["schemes"]]
    assert "Northbridge Bluechip Equity Fund" in names


def test_get_amc_detail_unknown_amc_returns_404():
    response = client.get("/api/amcs/999999999")
    assert response.status_code == 404
