"""Tests for database_writer.py against the real local Postgres database —
specifically the batching behavior in write_nav_records, added after a real
historical-backfill run against Supabase crashed mid-transfer
("SSL connection has been closed unexpectedly") on a single ~45,000-row,
180,000+-parameter INSERT for one month-chunk across the whole fund
universe. This exercises that a large call is split into several smaller
statements and still upserts every row correctly.
"""
from datetime import date, timedelta

import pytest

from app.core.database import SessionLocal
from app.models.reference import SchemeVariant
from app.models.timeseries import NavHistory
from data_pipeline.normalization.scheme_mapping import MappedNavRecord
from data_pipeline.storage.database_writer import get_or_create_data_source, write_nav_records
from data_pipeline.validation.nav_validation import ValidatedNavRecord

# Far in the future so this can never collide with real/seeded history.
_BASE_DATE = date(2098, 1, 1)
_ROW_COUNT = 6000  # comfortably more than _INSERT_BATCH_SIZE (5000), so batching is actually exercised


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_large_batch_is_split_and_fully_inserted(db):
    variant = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.isnot(None)).first()
    assert variant is not None, "requires Phase 2 seed data to be loaded"

    source = get_or_create_data_source(db, "Test Batching Source", "https://example.invalid", "manual")
    db.commit()

    mapped = [
        MappedNavRecord(
            scheme_variant_id=variant.id,
            record=ValidatedNavRecord(
                scheme_code=variant.amfi_code,
                isin_growth=None,
                isin_div_reinvestment=None,
                scheme_name="Batching Test Fixture",
                nav=100.0 + i * 0.01,
                nav_date=_BASE_DATE + timedelta(days=i),
            ),
        )
        for i in range(_ROW_COUNT)
    ]

    try:
        inserted = write_nav_records(db, source, mapped)
        db.commit()

        assert inserted == _ROW_COUNT

        count = (
            db.query(NavHistory)
            .filter(
                NavHistory.scheme_variant_id == variant.id,
                NavHistory.date >= _BASE_DATE,
                NavHistory.date < _BASE_DATE + timedelta(days=_ROW_COUNT),
            )
            .count()
        )
        assert count == _ROW_COUNT
    finally:
        db.query(NavHistory).filter(
            NavHistory.scheme_variant_id == variant.id,
            NavHistory.date >= _BASE_DATE,
            NavHistory.date < _BASE_DATE + timedelta(days=_ROW_COUNT),
        ).delete(synchronize_session=False)
        db.commit()


def test_rerunning_a_large_batch_is_idempotent(db):
    variant = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.isnot(None)).first()
    source = get_or_create_data_source(db, "Test Batching Source", "https://example.invalid", "manual")
    db.commit()

    mapped = [
        MappedNavRecord(
            scheme_variant_id=variant.id,
            record=ValidatedNavRecord(
                scheme_code=variant.amfi_code,
                isin_growth=None,
                isin_div_reinvestment=None,
                scheme_name="Batching Test Fixture",
                nav=100.0,
                nav_date=_BASE_DATE + timedelta(days=i),
            ),
        )
        for i in range(_ROW_COUNT)
    ]

    try:
        first = write_nav_records(db, source, mapped)
        db.commit()
        second = write_nav_records(db, source, mapped)
        db.commit()

        assert first == _ROW_COUNT
        assert second == 0  # every row already stored -> ON CONFLICT DO NOTHING across every sub-batch
    finally:
        db.query(NavHistory).filter(
            NavHistory.scheme_variant_id == variant.id,
            NavHistory.date >= _BASE_DATE,
            NavHistory.date < _BASE_DATE + timedelta(days=_ROW_COUNT),
        ).delete(synchronize_session=False)
        db.commit()
