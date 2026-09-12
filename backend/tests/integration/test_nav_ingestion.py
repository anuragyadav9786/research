"""End-to-end test of the NAV ingestion pipeline against the real local
Postgres database (Phase 2 seed data must be loaded). The network fetch is
monkeypatched — this exercises everything downstream of the HTTP call:
parse -> validate -> map -> store -> log — which is exactly the part that
*can* be verified in a sandboxed environment without outbound internet
access (see data_pipeline/sources/amfi/client.py's module docstring for
what still needs verifying against the live AMFI endpoint).
"""
from datetime import date

import pytest

import data_pipeline.ingestion.nav_ingestion as nav_ingestion_module
from app.core.database import SessionLocal
from app.models.reference import SchemeVariant
from app.models.timeseries import DataIngestionRun, DataSource, NavHistory
from data_pipeline.ingestion.nav_ingestion import DATA_SOURCE_NAME, run_amfi_nav_ingestion
from data_pipeline.sources.amfi.client import NavFetchError

TEST_NAV_DATE = date(2099, 1, 1)  # placeholder far-future date, can never collide with real/seeded history


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def _delete_run(db, run_id: int) -> None:
    # These pipeline tests exercise real writes against the shared dev
    # database (Phase 2's Postgres instance), including the operational
    # data_ingestion_runs log. Test-generated runs are cleaned up so that
    # log never mixes fake/test rows into what is meant to be a genuine
    # ingestion-health record (Rule 3: provenance must stay trustworthy).
    db.query(DataIngestionRun).filter(DataIngestionRun.id == run_id).delete()
    db.commit()


def _build_fixture_text(matched_amfi_code: str) -> str:
    return (
        "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date\n\n"
        "Open Ended Schemes(Equity Scheme)\n\n"
        "Sample Fixture Mutual Fund\n"
        f"{matched_amfi_code};-;-;Integration Test Fixture Fund;;;150.25;01-Jan-2099\n"
        # Blank Plan/Option (mirroring a real ETF-like row) so onboarding
        # can't create a scheme for these — this test is about NAV
        # matching/validation, not onboarding, so both stay unmatched.
        "999999;-;-;Unmapped Fixture Fund;;;99.99;01-Jan-2099\n"
        "888888;-;-;Bad NAV Fixture Fund;;;N.A.;01-Jan-2099\n"
    )


def test_full_pipeline_matches_seeded_variant_and_logs_run(db, monkeypatch):
    variant = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.isnot(None)).first()
    assert variant is not None, "requires Phase 2 seed data (database/seeds/seed_sample_data.py) to be loaded"

    fixture_text = _build_fixture_text(variant.amfi_code)
    monkeypatch.setattr(nav_ingestion_module, "fetch_navall", lambda: fixture_text)

    run = run_amfi_nav_ingestion(db)

    try:
        assert run.status == "success"
        assert run.records_downloaded == 3
        assert run.records_accepted == 1
        assert run.records_rejected == 2  # 1 unmapped scheme + 1 N.A. NAV

        source = db.query(DataSource).filter(DataSource.name == DATA_SOURCE_NAME).one()
        assert source.source_type == "amfi"

        stored = (
            db.query(NavHistory)
            .filter(NavHistory.scheme_variant_id == variant.id, NavHistory.date == TEST_NAV_DATE)
            .one()
        )
        assert float(stored.nav) == pytest.approx(150.25)
    finally:
        db.query(NavHistory).filter(
            NavHistory.scheme_variant_id == variant.id, NavHistory.date == TEST_NAV_DATE
        ).delete()
        db.commit()
        _delete_run(db, run.id)


def test_rerunning_ingestion_for_same_date_is_idempotent(db, monkeypatch):
    variant = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.isnot(None)).first()
    fixture_text = _build_fixture_text(variant.amfi_code)
    monkeypatch.setattr(nav_ingestion_module, "fetch_navall", lambda: fixture_text)

    try:
        first = run_amfi_nav_ingestion(db)
        second = run_amfi_nav_ingestion(db)

        assert first.records_accepted == 1
        assert second.records_accepted == 0  # already stored -> ON CONFLICT DO NOTHING, not an error

        count = (
            db.query(NavHistory)
            .filter(NavHistory.scheme_variant_id == variant.id, NavHistory.date == TEST_NAV_DATE)
            .count()
        )
        assert count == 1  # no duplicate row from the second run
    finally:
        db.query(NavHistory).filter(
            NavHistory.scheme_variant_id == variant.id, NavHistory.date == TEST_NAV_DATE
        ).delete()
        db.commit()
        _delete_run(db, first.id)
        _delete_run(db, second.id)


def test_ingestion_run_logged_as_failed_on_fetch_error(db, monkeypatch):
    def raise_fetch_error():
        raise NavFetchError("simulated network failure")

    monkeypatch.setattr(nav_ingestion_module, "fetch_navall", raise_fetch_error)

    run = run_amfi_nav_ingestion(db)

    try:
        assert run.status == "failed"
        assert "simulated network failure" in run.error_message
        assert run.records_accepted == 0
    finally:
        _delete_run(db, run.id)
