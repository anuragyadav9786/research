"""End-to-end test of the Phase 15 lazy, per-scheme NAV backfill against
the real local Postgres database (Phase 2 seed data must be loaded). The
network fetch is monkeypatched — this sandbox has no outbound internet
access at all — but everything downstream (parse, write, and the
nav_history_backfilled_at gate that makes repeat views a no-op) runs for
real.
"""
from datetime import date, datetime, timezone

import pytest

import data_pipeline.orchestration.lazy_nav_backfill as lazy_backfill_module
from app.core.database import SessionLocal
from app.models.reference import SchemeVariant
from app.models.timeseries import DataSource, NavHistory
from data_pipeline.orchestration.lazy_nav_backfill import DATA_SOURCE_NAME, ensure_nav_history
from data_pipeline.sources.mfapi.client import MfApiFetchError

FIXTURE_DATES = [date(2097, 1, 1), date(2097, 1, 2)]  # far-future, can never collide with real history


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def variant(db):
    v = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.isnot(None)).first()
    assert v is not None, "requires Phase 2 seed data to be loaded"
    original_backfilled_at = v.nav_history_backfilled_at
    original_amfi_code = v.amfi_code  # one test below sets this to None — must be restored, not just reset in memory
    v.nav_history_backfilled_at = None
    db.commit()
    yield v
    db.query(NavHistory).filter(
        NavHistory.scheme_variant_id == v.id, NavHistory.date.in_(FIXTURE_DATES)
    ).delete(synchronize_session=False)
    v.nav_history_backfilled_at = original_backfilled_at
    v.amfi_code = original_amfi_code
    db.commit()


def _fixture_body():
    return {
        "meta": {"scheme_code": 1, "scheme_name": "Fixture"},
        "data": [
            {"date": "02-01-2097", "nav": "150.50"},
            {"date": "01-01-2097", "nav": "150.25"},
        ],
        "status": "SUCCESS",
    }


def test_first_view_backfills_and_sets_flag(db, variant, monkeypatch):
    monkeypatch.setattr(lazy_backfill_module, "fetch_scheme_history", lambda code: _fixture_body())

    outcome = ensure_nav_history(db, variant)

    assert outcome.attempted is True
    assert outcome.success is True
    assert outcome.inserted == 2
    assert variant.nav_history_backfilled_at is not None

    source = db.query(DataSource).filter(DataSource.name == DATA_SOURCE_NAME).one()
    assert source.source_type == "mfapi"

    stored = (
        db.query(NavHistory)
        .filter(NavHistory.scheme_variant_id == variant.id, NavHistory.date == FIXTURE_DATES[1])
        .one()
    )
    assert float(stored.nav) == pytest.approx(150.50)


def test_second_view_is_a_noop_and_never_refetches(db, variant, monkeypatch):
    calls = []
    monkeypatch.setattr(
        lazy_backfill_module, "fetch_scheme_history", lambda code: (calls.append(code), _fixture_body())[1]
    )

    first = ensure_nav_history(db, variant)
    second = ensure_nav_history(db, variant)

    assert first.attempted is True
    assert second.attempted is False
    assert len(calls) == 1  # mfapi.in was only ever hit once


def test_variant_without_amfi_code_is_skipped(db, variant, monkeypatch):
    monkeypatch.setattr(lazy_backfill_module, "fetch_scheme_history", lambda code: _fixture_body())
    variant.amfi_code = None

    outcome = ensure_nav_history(db, variant)

    assert outcome.attempted is False
    assert variant.nav_history_backfilled_at is None


def test_failed_fetch_does_not_raise_and_leaves_flag_unset_for_retry(db, variant, monkeypatch):
    def raise_error(code):
        raise MfApiFetchError("simulated failure")

    monkeypatch.setattr(lazy_backfill_module, "fetch_scheme_history", raise_error)

    outcome = ensure_nav_history(db, variant)

    assert outcome.attempted is True
    assert outcome.success is False
    assert outcome.error == "simulated failure"
    assert variant.nav_history_backfilled_at is None  # so the next view retries
