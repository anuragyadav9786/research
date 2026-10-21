"""End-to-end test of the Phase 15 lazy, per-scheme NAV backfill against
the real local Postgres database (Phase 2 seed data must be loaded). The
network fetch is monkeypatched — this sandbox has no outbound internet
access at all — but everything downstream (parse, write, and the
nav_history_backfilled_at gate that makes repeat views a no-op) runs for
real.

Also covers the gap-repair path added after a real production bug: a
real fund (HDFC Flexi Cap Fund, Direct Growth) was found with a genuine
1,095-day hole in its NAV history despite nav_history_backfilled_at
being set — confirmed live that mfapi.in's own data had no such gap, so
a fresh fetch does repair it. See lazy_nav_backfill.py's module
docstring.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import data_pipeline.orchestration.lazy_nav_backfill as lazy_backfill_module
from app.core.database import SessionLocal
from app.models.reference import SchemeVariant
from app.models.timeseries import DataSource, NavHistory
from data_pipeline.orchestration.lazy_nav_backfill import (
    DATA_SOURCE_NAME,
    _GAP_RECHECK_COOLDOWN_DAYS,
    _GAP_THRESHOLD_DAYS,
    ensure_nav_history,
)
from data_pipeline.sources.mfapi.client import MfApiFetchError

FIXTURE_DATES = [date(2097, 1, 1), date(2097, 1, 2)]  # far-future, can never collide with real history
# The missing middle chunk a gap repair is expected to fill in --
# chronologically between FIXTURE_DATES ("old" data) and
# RECENT_FIXTURE_DATES ("current" data), so inserting FIXTURE_DATES and
# RECENT_FIXTURE_DATES alone (without this cluster) reproduces the real
# bug's shape: real data before and after a real hole in the middle.
GAPPED_FIXTURE_DATES = [date(2098, 6, 1), date(2098, 6, 2)]
# Stands in for "what the ongoing daily AMFI feed already wrote" on the
# far side of the gap -- present before any repair runs, same as the
# real bug (HDFC Flexi Cap Fund had current data right up to today, with
# the hole sitting years earlier).
RECENT_FIXTURE_DATES = [date(2099, 1, 1), date(2099, 1, 2)]


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
    original_gap_repair_at = v.nav_gap_repair_attempted_at
    original_amfi_code = v.amfi_code  # one test below sets this to None — must be restored, not just reset in memory

    # Snapshot and clear this variant's real nav_history so the gap-repair
    # tests below see only what they themselves insert -- a real gap
    # between genuine seeded history and the far-future fixture dates
    # (a decades-wide gap, purely a test artifact) would otherwise trip
    # the new gap check for reasons unrelated to what each test means to
    # exercise.
    original_nav_rows = [
        (r.date, r.nav, r.source_id)
        for r in db.query(NavHistory).filter(NavHistory.scheme_variant_id == v.id).all()
    ]
    db.query(NavHistory).filter(NavHistory.scheme_variant_id == v.id).delete(synchronize_session=False)

    v.nav_history_backfilled_at = None
    v.nav_gap_repair_attempted_at = None
    db.commit()
    yield v
    db.query(NavHistory).filter(NavHistory.scheme_variant_id == v.id).delete(synchronize_session=False)
    for nav_date, nav_value, source_id in original_nav_rows:
        db.add(NavHistory(scheme_variant_id=v.id, date=nav_date, nav=nav_value, source_id=source_id))
    v.nav_history_backfilled_at = original_backfilled_at
    v.nav_gap_repair_attempted_at = original_gap_repair_at
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


def _gapped_fixture_body():
    """The "repaired" mfapi.in response: all three clusters together
    (old + the previously-missing middle + recent), matching mfapi.in's
    real behavior of always returning a scheme's entire history in one
    call -- never just the missing sub-range."""
    return {
        "meta": {"scheme_code": 1, "scheme_name": "Fixture"},
        "data": [
            {"date": "02-01-2099", "nav": "999.0"},
            {"date": "01-01-2099", "nav": "999.0"},
            {"date": "02-06-2098", "nav": "200.50"},
            {"date": "01-06-2098", "nav": "200.25"},
            {"date": "02-01-2097", "nav": "150.50"},
            {"date": "01-01-2097", "nav": "150.25"},
        ],
        "status": "SUCCESS",
    }


def test_already_backfilled_variant_with_no_gap_does_not_refetch(db, variant, monkeypatch):
    """The common case: a variant backfilled once, with clean (ungapped)
    history, should never trigger a second mfapi.in call on later
    views -- the gap check is a local DB query, not a reason to refetch
    by itself."""
    calls = []
    monkeypatch.setattr(
        lazy_backfill_module, "fetch_scheme_history", lambda code: (calls.append(code), _fixture_body())[1]
    )
    first = ensure_nav_history(db, variant)
    assert first.attempted is True

    second = ensure_nav_history(db, variant)

    assert second.attempted is False
    assert len(calls) == 1


def _insert_recent_fixture_rows(db, variant):
    """Simulates the ongoing daily AMFI feed already having written
    "current" rows on the far side of the gap, independent of the lazy
    mfapi.in backfill -- matching the real bug's actual shape."""
    source_id = db.query(DataSource).filter(DataSource.name == DATA_SOURCE_NAME).one_or_none()
    if source_id is None:
        source_id = DataSource(name=DATA_SOURCE_NAME, url="https://api.mfapi.in", source_type="mfapi")
        db.add(source_id)
        db.flush()
    for d in RECENT_FIXTURE_DATES:
        db.add(NavHistory(scheme_variant_id=variant.id, date=d, nav=999.0, source_id=source_id.id))
    db.commit()


def test_already_backfilled_variant_with_real_gap_triggers_repair(db, variant, monkeypatch):
    """Reproduces the real bug's actual shape: real data before AND after
    a real hole, with nothing in between. The next view must detect it
    (a local query) and re-fetch mfapi.in's full history to repair it."""
    monkeypatch.setattr(lazy_backfill_module, "fetch_scheme_history", lambda code: _fixture_body())
    first = ensure_nav_history(db, variant)
    assert first.attempted is True
    assert first.success is True

    _insert_recent_fixture_rows(db, variant)  # the "current" cluster on the far side of the gap

    gap_days = (RECENT_FIXTURE_DATES[0] - FIXTURE_DATES[-1]).days
    assert gap_days > _GAP_THRESHOLD_DAYS, "test fixture must actually exceed the threshold"

    # Now mfapi.in's (mocked) response has been "fixed" upstream -- the
    # gap-repair path should close it.
    calls = []
    monkeypatch.setattr(
        lazy_backfill_module, "fetch_scheme_history", lambda code: (calls.append(code), _gapped_fixture_body())[1]
    )

    second = ensure_nav_history(db, variant)

    assert second.attempted is True
    assert second.success is True
    assert len(calls) == 1
    assert variant.nav_gap_repair_attempted_at is not None

    repaired = (
        db.query(NavHistory)
        .filter(NavHistory.scheme_variant_id == variant.id, NavHistory.date == GAPPED_FIXTURE_DATES[0])
        .one()
    )
    assert float(repaired.nav) == pytest.approx(200.25)


def test_gap_repair_respects_cooldown_after_a_failed_attempt(db, variant, monkeypatch):
    """A gap that didn't close on the last attempt must not be retried on
    every subsequent view within the cooldown window -- otherwise a
    permanently-unfixable gap (e.g. a delisted scheme) would cost one
    wasted mfapi.in call per page view forever."""
    monkeypatch.setattr(lazy_backfill_module, "fetch_scheme_history", lambda code: _fixture_body())
    ensure_nav_history(db, variant)  # first-time backfill, leaves a real gap for the next cluster

    db.add(
        NavHistory(
            scheme_variant_id=variant.id,
            date=GAPPED_FIXTURE_DATES[0],
            nav=200.50,
            source_id=db.query(DataSource).filter(DataSource.name == DATA_SOURCE_NAME).one().id,
        )
    )
    db.commit()
    variant.nav_gap_repair_attempted_at = datetime.now(timezone.utc)
    db.commit()

    calls = []
    monkeypatch.setattr(
        lazy_backfill_module, "fetch_scheme_history", lambda code: (calls.append(code), _gapped_fixture_body())[1]
    )

    outcome = ensure_nav_history(db, variant)

    assert outcome.attempted is False
    assert calls == []  # still within cooldown -- no wasted call


def test_gap_repair_retries_once_cooldown_has_elapsed(db, variant, monkeypatch):
    monkeypatch.setattr(lazy_backfill_module, "fetch_scheme_history", lambda code: _fixture_body())
    ensure_nav_history(db, variant)
    _insert_recent_fixture_rows(db, variant)  # a real gap must exist for this to exercise anything

    variant.nav_gap_repair_attempted_at = datetime.now(timezone.utc) - timedelta(
        days=_GAP_RECHECK_COOLDOWN_DAYS + 1
    )
    db.commit()

    calls = []
    monkeypatch.setattr(
        lazy_backfill_module, "fetch_scheme_history", lambda code: (calls.append(code), _gapped_fixture_body())[1]
    )

    outcome = ensure_nav_history(db, variant)

    assert outcome.attempted is True
    assert len(calls) == 1
