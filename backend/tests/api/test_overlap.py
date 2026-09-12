"""API tests for the Phase 8 pairwise fund overlap endpoint, against the
real Phase 2 seed data."""
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


def test_overlap_reports_common_holdings_and_weighted_overlap(bluechip_id, flexicap_id):
    response = client.get(f"/api/funds/{bluechip_id}/overlap", params={"compare_to": flexicap_id})
    assert response.status_code == 200
    body = response.json()

    assert body["available"] is True
    assert body["fund_a"]["id"] == bluechip_id
    assert body["fund_b"]["id"] == flexicap_id
    assert body["common_securities_count"] == 4
    # hand-computed: min(8.5,6.8)+min(9.8,6.1)+min(6.4,5.5)+min(4.8,5.3) = 6.8+6.1+5.5+4.8 = 23.2
    assert body["weighted_overlap_pct"] == pytest.approx(23.2)
    assert body["overlap_label"] == "moderate_overlap"
    assert -1.0 <= body["return_correlation"] <= 1.0

    # common_holdings sorted by min_weight descending
    min_weights = [h["min_weight"] for h in body["common_holdings"]]
    assert min_weights == sorted(min_weights, reverse=True)
    assert len(body["common_holdings"]) == 4


def test_overlap_is_symmetric_in_weighted_pct(bluechip_id, flexicap_id):
    forward = client.get(f"/api/funds/{bluechip_id}/overlap", params={"compare_to": flexicap_id}).json()
    reverse = client.get(f"/api/funds/{flexicap_id}/overlap", params={"compare_to": bluechip_id}).json()
    assert forward["weighted_overlap_pct"] == pytest.approx(reverse["weighted_overlap_pct"])
    assert forward["common_securities_count"] == reverse["common_securities_count"]


def test_overlap_self_comparison_rejected(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/overlap", params={"compare_to": bluechip_id})
    assert response.status_code == 400


def test_overlap_unknown_compare_to_returns_404(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/overlap", params={"compare_to": 999999})
    assert response.status_code == 404


def test_overlap_missing_query_param_returns_422(bluechip_id):
    response = client.get(f"/api/funds/{bluechip_id}/overlap")
    assert response.status_code == 422
