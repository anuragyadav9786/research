"""Persists validated, mapped NAV records — the only place in the NAV
ingestion pipeline that touches the database for writes."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.timeseries import BenchmarkHistory, DataSource, NavHistory
from data_pipeline.normalization.scheme_mapping import MappedNavRecord
from data_pipeline.validation.benchmark_validation import ValidatedBenchmarkPoint


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


def _batched_upsert(db: Session, model, rows: list[dict], constraint: str) -> int:
    """Shared batched-upsert core behind write_nav_records, write_nav_points
    and write_benchmark_points. Uses INSERT ... ON CONFLICT DO NOTHING
    against the given unique constraint, so re-running for a (variant,
    date) or (benchmark, date) pair already stored is a safe no-op rather
    than a unique-constraint error. Returns the number of rows actually
    inserted (conflicts don't count).
    """
    if not rows:
        return 0

    inserted = 0
    for i in range(0, len(rows), _INSERT_BATCH_SIZE):
        batch = rows[i : i + _INSERT_BATCH_SIZE]
        stmt = pg_insert(model).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint=constraint)
        result = db.execute(stmt)
        inserted += result.rowcount or 0
    return inserted


def _insert_nav_rows(db: Session, rows: list[dict]) -> int:
    return _batched_upsert(db, NavHistory, rows, constraint="uq_nav_variant_date")


def write_nav_records(db: Session, source: DataSource, mapped: list[MappedNavRecord]) -> int:
    """Upsert NAV rows for AMFI-file-sourced records (daily feed and bulk
    historical backfill), keyed on (scheme_variant_id, date). See
    _insert_nav_rows for the batching/upsert mechanics.
    """
    rows = [
        {
            "scheme_variant_id": m.scheme_variant_id,
            "date": m.record.nav_date,
            "nav": m.record.nav,
            "source_id": source.id,
        }
        for m in mapped
    ]
    return _insert_nav_rows(db, rows)


def write_nav_points(
    db: Session, source: DataSource, scheme_variant_id: int, points: list[tuple[date, float]]
) -> int:
    """Upsert NAV rows for a single scheme_variant from a list of (date,
    nav) points — the shape data_pipeline/orchestration/lazy_nav_backfill.py
    (the mfapi.in-based on-demand per-scheme backfill) produces. Unlike
    write_nav_records, the caller already knows exactly which
    scheme_variant it's writing for, so there's no AMFI-shaped
    ValidatedNavRecord/MappedNavRecord to unwrap — just the identity this
    table actually stores. See _insert_nav_rows for the batching/upsert
    mechanics.
    """
    rows = [
        {"scheme_variant_id": scheme_variant_id, "date": d, "nav": nav, "source_id": source.id}
        for d, nav in points
    ]
    return _insert_nav_rows(db, rows)


def write_benchmark_points(
    db: Session, source: DataSource, benchmark_id: int, points: list[ValidatedBenchmarkPoint]
) -> int:
    """Upsert price rows for a single benchmark — shared across every
    scheme that uses it, never written per-fund (see BenchmarkHistory's
    docstring). Used by
    data_pipeline/orchestration/lazy_benchmark_backfill.py. Same
    ON CONFLICT DO NOTHING mechanics as write_nav_points, against
    uq_benchmark_date, so re-fetching a date already stored is a no-op.
    """
    rows = [
        {"benchmark_id": benchmark_id, "date": p.price_date, "value": p.value, "source_id": source.id}
        for p in points
    ]
    return _batched_upsert(db, BenchmarkHistory, rows, constraint="uq_benchmark_date")
