"""CLI entry point for backfilling historical NAV data from AMFI (see
data_pipeline/orchestration/historical_backfill.py for the chunking and
matching logic this drives).

Usage (from the repo root, DATABASE_URL pointing at the same database the
backend uses):

    python -m data_pipeline.orchestration.run_historical_backfill \
        --start 01-Jan-2023 --end 12-Sep-2026

Both flags are optional; default is the last 3 years through today —
enough history for meaningful 1Y/3Y annualized returns without an
excessively long run (see historical_backfill.py's module docstring for
the per-request timing this is sized against: roughly 0.45s of AMFI
response time per calendar day requested, plus a courteous delay between
each month-chunk).

Only ever matches against scheme_variants already onboarded from the live
NAVAll.txt feed (data_pipeline/orchestration/daily_pipeline.py) — run that
first if the database has no schemes yet.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

# Run via `python -m data_pipeline.orchestration.run_historical_backfill`
# from the repo root, so backend/ (holding the `app` package) isn't on
# sys.path unless added explicitly — mirrors daily_pipeline.py's bootstrap.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.core.database import SessionLocal  # noqa: E402
from data_pipeline.orchestration.historical_backfill import run_historical_backfill  # noqa: E402


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%d-%b-%Y").date()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=_parse_date, default=None, help="DD-Mon-YYYY, default: 3 years before --end")
    parser.add_argument("--end", type=_parse_date, default=None, help="DD-Mon-YYYY, default: today")
    args = parser.parse_args()

    end = args.end or date.today()
    start = args.start or (end - timedelta(days=365 * 3))
    if start > end:
        parser.error(f"--start ({start}) must not be after --end ({end})")

    print(f"Historical NAV backfill {start} to {end} — starting, one line per month-chunk as it completes:")

    db = SessionLocal()
    try:
        result = run_historical_backfill(db, start, end)
    finally:
        db.close()

    total_downloaded = sum(c.downloaded for c in result.chunks)
    total_accepted = sum(c.accepted for c in result.chunks)
    total_rejected = sum(c.rejected for c in result.chunks)
    total_inserted = sum(c.inserted for c in result.chunks)
    failed_chunks = [c for c in result.chunks if c.error]

    print(
        f"\nHistorical NAV backfill {start} to {end}: {len(result.chunks)} month-chunk(s) — "
        f"downloaded={total_downloaded} accepted={total_accepted} rejected={total_rejected} inserted={total_inserted}"
    )

    if failed_chunks:
        print(f"\n{len(failed_chunks)} chunk(s) failed — re-run with the same --start/--end to retry "
              f"(already-inserted rows are skipped via ON CONFLICT DO NOTHING).")
        sys.exit(1)


if __name__ == "__main__":
    main()
