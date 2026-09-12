"""Persists validated, mapped NAV records — the only place in the NAV
ingestion pipeline that touches the database for writes."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.timeseries import DataSource, NavHistory
from data_pipeline.normalization.scheme_mapping import MappedNavRecord


def get_or_create_data_source(db: Session, name: str, url: str, source_type: str) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.name == name))
    if source is None:
        source = DataSource(name=name, url=url, source_type=source_type)
        db.add(source)
        db.flush()
    return source


def write_nav_records(db: Session, source: DataSource, mapped: list[MappedNavRecord]) -> int:
    """Upsert NAV rows, keyed on (scheme_variant_id, date).

    Uses INSERT ... ON CONFLICT DO NOTHING against the existing
    uq_nav_variant_date constraint, so re-running ingestion for a date
    already stored is a safe no-op rather than a unique-constraint error —
    daily ingestion runs are expected to be re-run/retried.

    Returns the number of rows actually inserted (conflicts don't count).
    """
    if not mapped:
        return 0

    rows = [
        {
            "scheme_variant_id": m.scheme_variant_id,
            "date": m.record.nav_date,
            "nav": m.record.nav,
            "source_id": source.id,
        }
        for m in mapped
    ]
    stmt = pg_insert(NavHistory).values(rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_nav_variant_date")
    result = db.execute(stmt)
    return result.rowcount or 0
