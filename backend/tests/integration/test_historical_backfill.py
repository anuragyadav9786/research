"""End-to-end test of the historical NAV backfill pipeline against the real
local Postgres database (Phase 2 seed data must be loaded). The network
fetch is monkeypatched per month-chunk — this exercises the chunking,
parse -> validate -> map -> store flow, and per-chunk failure isolation
(the parts verifiable without outbound internet access; see
data_pipeline/sources/amfi/client.py's module docstring).
"""
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

import data_pipeline.orchestration.historical_backfill as backfill_module
from app.core.database import SessionLocal
from app.models.reference import SchemeVariant
from app.models.timeseries import DataSource, NavHistory
from data_pipeline.orchestration.historical_backfill import DATA_SOURCE_NAME, run_historical_backfill
from data_pipeline.sources.amfi.client import NavFetchError

# Far-future placeholder dates, one per month-chunk exercised below — can
# never collide with real/seeded history.
JAN_DATE = date(2099, 1, 15)
FEB_DATE = date(2099, 2, 5)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def _fixture_for(amfi_code: str, nav_date: date) -> str:
    date_str = nav_date.strftime("%d-%b-%Y")
    return (
        "Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date\n\n"
        f"{amfi_code};Integration Test Fixture Fund - Direct - Growth;Direct;Growth;-;-;150.25;{date_str}\n"
        f"999999;Unmapped Fixture Fund;Direct;Growth;-;-;99.99;{date_str}\n"
    )


def _month_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["frmdt"][0].split("-")[1]


def test_backfill_matches_seeded_variant_across_month_chunks(db, monkeypatch):
    variant = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.isnot(None)).first()
    assert variant is not None, "requires Phase 2 seed data (database/seeds/seed_sample_data.py) to be loaded"

    def fake_fetch(url, timeout=None):
        nav_date = JAN_DATE if _month_of(url) == "Jan" else FEB_DATE
        return _fixture_for(variant.amfi_code, nav_date)

    monkeypatch.setattr(backfill_module, "fetch_navall", fake_fetch)

    try:
        result = run_historical_backfill(db, JAN_DATE.replace(day=1), FEB_DATE, request_delay_seconds=0)

        assert len(result.chunks) == 2
        assert sum(c.inserted for c in result.chunks) == 2
        assert sum(c.accepted for c in result.chunks) == 4  # both the matched and unmapped row validate fine
        assert sum(c.rejected for c in result.chunks) == 2  # one unmapped row per chunk

        source = db.query(DataSource).filter(DataSource.name == DATA_SOURCE_NAME).one()
        assert source.source_type == "amfi"

        for nav_date in (JAN_DATE, FEB_DATE):
            stored = (
                db.query(NavHistory)
                .filter(NavHistory.scheme_variant_id == variant.id, NavHistory.date == nav_date)
                .one()
            )
            assert float(stored.nav) == pytest.approx(150.25)
    finally:
        db.query(NavHistory).filter(
            NavHistory.scheme_variant_id == variant.id, NavHistory.date.in_([JAN_DATE, FEB_DATE])
        ).delete(synchronize_session=False)
        db.commit()


def test_backfill_is_idempotent_across_reruns(db, monkeypatch):
    variant = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.isnot(None)).first()

    monkeypatch.setattr(backfill_module, "fetch_navall", lambda url, timeout=None: _fixture_for(variant.amfi_code, JAN_DATE))

    try:
        first = run_historical_backfill(db, JAN_DATE, JAN_DATE, request_delay_seconds=0)
        second = run_historical_backfill(db, JAN_DATE, JAN_DATE, request_delay_seconds=0)

        assert sum(c.inserted for c in first.chunks) == 1
        assert sum(c.inserted for c in second.chunks) == 0  # already stored -> ON CONFLICT DO NOTHING

        count = (
            db.query(NavHistory)
            .filter(NavHistory.scheme_variant_id == variant.id, NavHistory.date == JAN_DATE)
            .count()
        )
        assert count == 1
    finally:
        db.query(NavHistory).filter(
            NavHistory.scheme_variant_id == variant.id, NavHistory.date == JAN_DATE
        ).delete()
        db.commit()


def test_backfill_records_a_failed_chunk_without_losing_others(db, monkeypatch):
    variant = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.isnot(None)).first()

    def fake_fetch(url, timeout=None):
        if _month_of(url) == "Jan":
            raise NavFetchError("simulated timeout")
        return _fixture_for(variant.amfi_code, FEB_DATE)

    monkeypatch.setattr(backfill_module, "fetch_navall", fake_fetch)

    try:
        result = run_historical_backfill(db, JAN_DATE.replace(day=1), FEB_DATE, request_delay_seconds=0)

        assert len(result.chunks) == 2
        assert result.chunks[0].error == "simulated timeout"
        assert result.chunks[1].error is None
        assert result.chunks[1].inserted == 1
    finally:
        db.query(NavHistory).filter(
            NavHistory.scheme_variant_id == variant.id, NavHistory.date == FEB_DATE
        ).delete()
        db.commit()
