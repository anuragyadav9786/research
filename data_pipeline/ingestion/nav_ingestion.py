"""Orchestrates one AMFI NAV ingestion run: fetch -> parse -> onboard ->
validate -> map -> store -> log.

Every run produces a `data_ingestion_runs` row (Section 19/34) regardless
of outcome — including failures — so "is the data fresh, and did the last
attempt succeed?" is always answerable from the database, never just from
a log file that might not be checked.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.timeseries import DataIngestionRun
from data_pipeline.normalization.scheme_mapping import map_to_scheme_variants
from data_pipeline.normalization.scheme_onboarding import onboard_schemes
from data_pipeline.sources.amfi.client import NAVALL_URL, NavFetchError, fetch_navall
from data_pipeline.sources.amfi.parser import parse_navall
from data_pipeline.storage.database_writer import get_or_create_data_source, write_nav_records
from data_pipeline.validation.nav_validation import validate_navall_records

DATA_SOURCE_NAME = "AMFI NAVAll.txt"


def run_amfi_nav_ingestion(db: Session) -> DataIngestionRun:
    source = get_or_create_data_source(db, DATA_SOURCE_NAME, NAVALL_URL, "amfi")
    db.commit()  # persist the source row even if everything below fails

    run = DataIngestionRun(
        source_id=source.id,
        records_downloaded=0,
        records_accepted=0,
        records_rejected=0,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        raw_text = fetch_navall()
        raw_records = parse_navall(raw_text)
        run.records_downloaded = len(raw_records)

        # Create real AMC/Scheme/SchemeVariant rows for schemes this file
        # describes that we don't yet track, before mapping — so a scheme
        # onboarded from today's file can also have today's NAV stored
        # against it, not just from tomorrow's run. See scheme_onboarding.py
        # for what is and isn't onboarded (e.g. most ETFs are skipped, not
        # guessed at).
        onboarding = onboard_schemes(db, raw_records)
        run.onboarding_summary = onboarding  # not persisted — for the caller's log line only

        validation = validate_navall_records(raw_records)
        mapping = map_to_scheme_variants(db, validation.accepted)

        inserted = write_nav_records(db, source, mapping.matched)

        run.records_accepted = inserted
        run.records_rejected = len(validation.rejected) + len(mapping.unmatched)
        run.status = "success"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run

    except NavFetchError as exc:
        db.rollback()
        return _mark_failed(db, run.id, str(exc))
    except Exception as exc:  # noqa: BLE001 — any unexpected failure must still be logged, never silent
        db.rollback()
        _mark_failed(db, run.id, f"Unexpected ingestion error: {exc}")
        raise


def _mark_failed(db: Session, run_id: int, message: str) -> DataIngestionRun:
    # The rollback above expires/detaches `run` from the session, so the
    # failed run is re-fetched by its already-committed primary key rather
    # than reusing the stale in-memory object.
    run = db.get(DataIngestionRun, run_id)
    run.status = "failed"
    run.error_message = message[:2000]
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run
