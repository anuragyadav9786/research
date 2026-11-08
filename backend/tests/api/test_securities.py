"""API tests for the cross-fund security lookup endpoints, run against
the real local Postgres database with Phase 2 seed data loaded (same
pattern as tests/api/test_funds.py). Read-only against existing seed
data -- no cleanup needed.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import Security

client = TestClient(app)


@pytest.fixture(scope="module")
def seeded_security_id() -> int:
    db = SessionLocal()
    try:
        security = db.query(Security).filter(Security.isin == "SAMPLE-ISIN-0001").first()
        assert security is not None, "requires Phase 2 seed data to be loaded"
        return security.id
    finally:
        db.close()


def test_search_securities_by_name_substring(seeded_security_id):
    response = client.get("/api/securities/search", params={"q": "Sample Bank"})
    assert response.status_code == 200
    ids = [s["id"] for s in response.json()["items"]]
    assert seeded_security_id in ids


def test_search_securities_by_isin_substring(seeded_security_id):
    response = client.get("/api/securities/search", params={"q": "SAMPLE-ISIN-0001"})
    assert response.status_code == 200
    ids = [s["id"] for s in response.json()["items"]]
    assert seeded_security_id in ids


def test_search_securities_no_match_returns_empty_list():
    response = client.get("/api/securities/search", params={"q": "NoSuchSecurityNameXYZ"})
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_search_securities_requires_non_empty_query():
    response = client.get("/api/securities/search", params={"q": ""})
    assert response.status_code == 422


def test_get_security_holders_returns_expected_shape(seeded_security_id):
    response = client.get(f"/api/securities/{seeded_security_id}/holders")
    assert response.status_code == 200
    body = response.json()
    assert body["security"]["id"] == seeded_security_id
    assert body["total_holders"] == len(body["holders"])
    for holder in body["holders"]:
        assert set(holder.keys()) == {"scheme_id", "scheme_name", "amc_name", "as_of_date", "weight_pct", "market_value"}


def test_get_security_holders_unknown_security_returns_404():
    response = client.get("/api/securities/999999999/holders")
    assert response.status_code == 404
