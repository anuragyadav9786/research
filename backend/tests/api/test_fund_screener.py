"""API tests for GET /api/funds/screener, run against the real local
Postgres database with Phase 2 seed data loaded. Seeds its own
fund_period_returns rows directly (bypassing the rollup job itself,
which is tested separately in tests/integration/
test_period_return_rollup.py) and cleans them up afterward.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import Scheme, SchemeVariant
from app.models.timeseries import DataSource, FundPeriodReturn

client = TestClient(app)

AS_OF = date(2026, 10, 20)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def two_seeded_funds_with_returns(db):
    bluechip = db.query(Scheme).filter(Scheme.name == "Northbridge Bluechip Equity Fund").first()
    flexicap = db.query(Scheme).filter(Scheme.name == "Northbridge Flexi Cap Fund").first()
    assert bluechip is not None and flexicap is not None, "requires Phase 2 seed data to be loaded"

    bluechip_variant = db.query(SchemeVariant).filter(
        SchemeVariant.scheme_id == bluechip.id, SchemeVariant.plan == "regular"
    ).first()
    flexicap_variant = db.query(SchemeVariant).filter(
        SchemeVariant.scheme_id == flexicap.id, SchemeVariant.plan == "regular"
    ).first()

    source = DataSource(name="TEST FUND SCREENER SOURCE", source_type="manual")
    db.add(source)
    db.flush()

    rows = [
        FundPeriodReturn(
            scheme_variant_id=bluechip_variant.id, period="1y", return_pct=12.5,
            as_of_date=AS_OF, anchor_date=date(2025, 10, 20), source_id=source.id,
        ),
        FundPeriodReturn(
            scheme_variant_id=flexicap_variant.id, period="1y", return_pct=18.0,
            as_of_date=AS_OF, anchor_date=date(2025, 10, 20), source_id=source.id,
        ),
        # Bluechip has no 3y row at all -> must surface as DATA_UNAVAILABLE,
        # never a fabricated/omitted value.
        FundPeriodReturn(
            scheme_variant_id=flexicap_variant.id, period="3y", return_pct=45.0,
            as_of_date=AS_OF, anchor_date=date(2023, 10, 20), source_id=source.id,
        ),
    ]
    db.add_all(rows)
    db.commit()

    yield {"bluechip_scheme_id": bluechip.id, "flexicap_scheme_id": flexicap.id}

    db.query(FundPeriodReturn).filter(
        FundPeriodReturn.scheme_variant_id.in_([bluechip_variant.id, flexicap_variant.id])
    ).delete(synchronize_session=False)
    db.query(DataSource).filter(DataSource.id == source.id).delete()
    db.commit()


def test_screener_sorts_descending_by_default(two_seeded_funds_with_returns):
    response = client.get("/api/funds/screener", params={"sort_by": "1y"})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["sort_by"] == "1y"
    assert body["sort_dir"] == "desc"
    assert body["as_of_date"] == "2026-10-20"

    ids = [item["id"] for item in body["items"]]
    flexicap_idx = ids.index(two_seeded_funds_with_returns["flexicap_scheme_id"])
    bluechip_idx = ids.index(two_seeded_funds_with_returns["bluechip_scheme_id"])
    assert flexicap_idx < bluechip_idx  # 18.0% ranks above 12.5% in a descending sort


def test_screener_reports_data_unavailable_never_fabricated_zero(two_seeded_funds_with_returns):
    response = client.get("/api/funds/screener", params={"sort_by": "3y"})
    assert response.status_code == 200, response.text
    body = response.json()

    bluechip_entry = next(
        item for item in body["items"] if item["id"] == two_seeded_funds_with_returns["bluechip_scheme_id"]
    )
    assert bluechip_entry["returns"]["3y"]["status"] == "DATA_UNAVAILABLE"
    assert bluechip_entry["returns"]["3y"]["return_pct"] is None

    flexicap_entry = next(
        item for item in body["items"] if item["id"] == two_seeded_funds_with_returns["flexicap_scheme_id"]
    )
    assert flexicap_entry["returns"]["3y"] == {
        "return_pct": 45.0, "status": "VALID", "anchor_date": "2023-10-20",
    }

    # Missing values sort last even in a "3y" descending sort -- bluechip's
    # unavailable 3y figure must never read as beating a real number.
    ids = [item["id"] for item in body["items"]]
    assert ids.index(two_seeded_funds_with_returns["flexicap_scheme_id"]) < ids.index(
        two_seeded_funds_with_returns["bluechip_scheme_id"]
    )


def test_screener_ascending_sort(two_seeded_funds_with_returns):
    response = client.get("/api/funds/screener", params={"sort_by": "1y", "sort_dir": "asc"})
    assert response.status_code == 200, response.text
    ids = [item["id"] for item in response.json()["items"]]
    bluechip_idx = ids.index(two_seeded_funds_with_returns["bluechip_scheme_id"])
    flexicap_idx = ids.index(two_seeded_funds_with_returns["flexicap_scheme_id"])
    assert bluechip_idx < flexicap_idx  # 12.5% now ranks first ascending


def test_screener_disclaimer_present_and_not_framed_as_a_ranking(two_seeded_funds_with_returns):
    response = client.get("/api/funds/screener")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "does not guarantee future results" in body["disclaimer"]


def test_screener_invalid_sort_by_returns_422():
    response = client.get("/api/funds/screener", params={"sort_by": "10y"})
    assert response.status_code == 422
