"""Entry point for the daily NAV refresh (Section 29 Phase 13 automation).

Not yet wired to a GitHub Actions workflow — doing so requires a deployed
database reachable from CI (a `DATABASE_URL` secret pointing at a
provisioned Postgres instance, e.g. Supabase), which does not exist yet at
this stage of the build. Wire this in once that's provisioned, as:

    python -m data_pipeline.orchestration.daily_pipeline

running with the same DATABASE_URL the backend uses.
"""
from __future__ import annotations

from app.core.database import SessionLocal
from data_pipeline.ingestion.nav_ingestion import run_amfi_nav_ingestion


def main() -> None:
    db = SessionLocal()
    try:
        run = run_amfi_nav_ingestion(db)
        print(
            f"NAV ingestion run {run.id}: status={run.status} "
            f"downloaded={run.records_downloaded} accepted={run.records_accepted} "
            f"rejected={run.records_rejected}"
            + (f" error={run.error_message}" if run.error_message else "")
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
