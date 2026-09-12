"""Entry point for the daily NAV refresh (Section 29 Phase 13 automation).

Wired to .github/workflows/daily-nav-ingestion.yml, run as:

    python -m data_pipeline.orchestration.daily_pipeline

with DATABASE_URL pointing at the same database the backend uses. That
workflow's schedule trigger is commented out until a real, CI-reachable
Postgres instance (e.g. Supabase) is provisioned and its DATABASE_URL
added as a repository secret — see docs/deployment.md. Until then this
can still be run manually (`workflow_dispatch`) or from a local machine.
"""
from __future__ import annotations

import os
import sys

# Run via `python -m data_pipeline.orchestration.daily_pipeline` from the
# repo root, so backend/ (holding the `app` package) isn't on sys.path
# unless added explicitly — mirrors the same bootstrap already used by
# backend/conftest.py and database/migrations/env.py.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.core.database import SessionLocal  # noqa: E402
from data_pipeline.ingestion.nav_ingestion import run_amfi_nav_ingestion  # noqa: E402
from data_pipeline.orchestration.precompute_metrics import run_precompute  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        run = run_amfi_nav_ingestion(db)
        onboarding = getattr(run, "onboarding_summary", None)
        onboarding_msg = ""
        if onboarding is not None:
            onboarding_msg = (
                f" | onboarded: amcs={onboarding.amcs_created} fund_families={onboarding.fund_families_created} "
                f"schemes={onboarding.schemes_created} variants={onboarding.variants_created} "
                f"skipped={len(onboarding.skipped)}"
            )
            if onboarding.skipped:
                from collections import Counter

                reason_counts = Counter(s.reason for s in onboarding.skipped)
                onboarding_msg += " (" + ", ".join(f"{r}={c}" for r, c in reason_counts.most_common()) + ")"
                for sample in onboarding.skipped[:5]:
                    print(f"  skip sample: code={sample.scheme_code!r} name={sample.scheme_name!r} reason={sample.reason!r}")
        print(
            f"NAV ingestion run {run.id}: status={run.status} "
            f"downloaded={run.records_downloaded} accepted={run.records_accepted} "
            f"rejected={run.records_rejected}"
            + (f" error={run.error_message}" if run.error_message else "")
            + onboarding_msg
        )

        # Only worth recomputing analytics against a NAV set that just
        # updated cleanly — a failed ingestion run means today's nav_history
        # is whatever yesterday's precompute already saw, so skip re-doing
        # that work rather than pointlessly re-running it.
        if run.status == "success":
            precompute = run_precompute(db)
            print(
                f"Metrics precompute: variants_processed={precompute.variants_processed} "
                f"variants_skipped_no_history={precompute.variants_skipped_no_history} "
                f"metrics_written={precompute.metrics_written}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
