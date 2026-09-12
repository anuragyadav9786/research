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


# Postgres hard-caps a single statement at 65535 bind parameters; this
# table's INSERT uses 4 columns/row, so 65535/4 ≈ 16383 rows is the actual
# ceiling. A one-off daily ingestion run (one row per scheme) never gets
# close to that, but a historical-backfill month-chunk (every trading day
# in the month, for the whole fund universe, all matched and written in
# one call) can be an order of magnitude larger — a real run hit this: one
# ~45,000-row `.values(rows)` call compiled a single INSERT with 180,000+
# parameters, which Supabase's pooled connection dropped mid-transfer
# ("SSL connection has been closed unexpectedly") rather than rejecting
# outright. Batching keeps every individual statement small regardless of
# how many rows the caller passes in one call.
_INSERT_BATCH_SIZE = 5000


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

    inserted = 0
    for i in range(0, len(rows), _INSERT_BATCH_SIZE):
        batch = rows[i : i + _INSERT_BATCH_SIZE]
        stmt = pg_insert(NavHistory).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_nav_variant_date")
        result = db.execute(stmt)
        inserted += result.rowcount or 0
    return inserted
