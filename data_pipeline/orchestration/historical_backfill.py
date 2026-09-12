"""One-time (or periodic) historical NAV backfill from AMFI's historical
NAV report endpoint (DownloadNAVHistoryReport_Po.aspx) — see
data_pipeline/sources/amfi/historical_parser.py for the endpoint's column
format and why it never onboards new schemes.

Chunked by calendar month. Sizing rationale, measured against the real
endpoint via a GitHub Actions debug run (see git history): a 1-month range
took 14.1s / 23.9MB, a 3-month range took 41.0s / 74.0MB, and an 8-month
single request reproducibly timed out server-side around 45s. Monthly
chunks stay comfortably inside that envelope — more requests, but this
only needs to run occasionally (a one-time backfill, or extending
coverage further back), not daily like the live feed.

Each chunk is fetched, validated (see validate_historical_records — a
scheme_code legitimately repeats once per date here, unlike the live
single-day snapshot), matched against already-onboarded scheme_variants,
written, and committed independently. A mid-run failure (a single chunk's
fetch timing out, say) doesn't lose the chunks already committed, and
re-running the same range is safe: `write_nav_records` upserts on
(scheme_variant_id, date) with ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import time
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx
from sqlalchemy.orm import Session

from data_pipeline.normalization.scheme_mapping import map_to_scheme_variants
from data_pipeline.sources.amfi.client import NavFetchError, fetch_navall
from data_pipeline.sources.amfi.historical_parser import parse_historical_navall
from data_pipeline.storage.database_writer import get_or_create_data_source, write_nav_records
from data_pipeline.validation.nav_validation import validate_historical_records

HISTORICAL_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"
DATA_SOURCE_NAME = "AMFI Historical NAV Report (backfill)"

# A firm read cap, not just an inter-chunk one — see historical_backfill's
# own investigation of httpx's timeout=<float> semantics in git history
# (a plain float only bounds gaps BETWEEN received chunks, not total
# request duration, which let a prior probe run 9+ minutes unnoticed).
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0)

# Courteous spacing between requests to AMFI's server — this is a bulk
# backfill hitting the same host dozens of times in a row, not a single
# daily fetch.
DEFAULT_REQUEST_DELAY_SECONDS = 3.0


@dataclass
class MonthChunkResult:
    frmdt: str
    todt: str
    downloaded: int = 0
    accepted: int = 0
    rejected: int = 0
    inserted: int = 0
    error: str | None = None


@dataclass
class BackfillResult:
    chunks: list[MonthChunkResult] = field(default_factory=list)


def _month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] into whole calendar-month (chunk_start, chunk_end) pairs."""
    if start > end:
        return []
    chunks: list[tuple[date, date]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        last_day = monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, last_day)
        chunk_start = max(cursor, start)
        chunk_end = min(month_end, end)
        chunks.append((chunk_start, chunk_end))
        cursor = month_end + timedelta(days=1)
    return chunks


def _fmt(d: date) -> str:
    return d.strftime("%d-%b-%Y")


def run_historical_backfill(
    db: Session,
    start: date,
    end: date,
    *,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
) -> BackfillResult:
    source = get_or_create_data_source(db, DATA_SOURCE_NAME, HISTORICAL_URL, "amfi")
    db.commit()  # persist the source row even if every chunk below fails

    result = BackfillResult()
    chunk_ranges = _month_chunks(start, end)

    for index, (chunk_start, chunk_end) in enumerate(chunk_ranges):
        frmdt, todt = _fmt(chunk_start), _fmt(chunk_end)
        chunk_result = MonthChunkResult(frmdt=frmdt, todt=todt)
        url = f"{HISTORICAL_URL}?tp=1&frmdt={frmdt}&todt={todt}"

        try:
            raw_text = fetch_navall(url, timeout=timeout)
        except NavFetchError as exc:
            chunk_result.error = str(exc)
            result.chunks.append(chunk_result)
            print(f"  [{index + 1}/{len(chunk_ranges)}] {frmdt} to {todt}: FAILED: {exc}", flush=True)
            if index < len(chunk_ranges) - 1:
                time.sleep(request_delay_seconds)
            continue

        raw_records = parse_historical_navall(raw_text)
        chunk_result.downloaded = len(raw_records)

        validation = validate_historical_records(raw_records)
        mapping = map_to_scheme_variants(db, validation.accepted)
        inserted = write_nav_records(db, source, mapping.matched)
        db.commit()

        chunk_result.accepted = len(validation.accepted)
        chunk_result.rejected = len(validation.rejected) + len(mapping.unmatched)
        chunk_result.inserted = inserted
        result.chunks.append(chunk_result)

        # Printed as each chunk finishes, not just in the caller's final
        # summary — a multi-year backfill can run for tens of minutes, and
        # a mid-run failure (see write_nav_records' batching note above for
        # a real example) should leave visible progress up to that point,
        # not only a traceback with no context for how far it got.
        print(
            f"  [{index + 1}/{len(chunk_ranges)}] {frmdt} to {todt}: downloaded={chunk_result.downloaded} "
            f"accepted={chunk_result.accepted} rejected={chunk_result.rejected} inserted={chunk_result.inserted}",
            flush=True,
        )

        if index < len(chunk_ranges) - 1:
            time.sleep(request_delay_seconds)

    return result
