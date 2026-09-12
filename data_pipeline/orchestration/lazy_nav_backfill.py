"""On-demand, per-scheme NAV history backfill via api.mfapi.in.

Supersedes the full-fund-universe bulk backfill (see git history:
historical_backfill.py, now removed) — that approach downloaded and
matched EVERY onboarded scheme's NAV for every month in the backfill
window, whether or not anyone had ever looked at most of those funds. On a
free-tier Postgres instance (Supabase), that meant storing hundreds of
thousands of rows for funds nobody researches, purely on the chance
someone might.

Here, a scheme_variant's full history is instead fetched the FIRST time
its research page is actually requested (see app/api/funds.py's
_resolve_variant, which calls ensure_nav_history on every lookup), then
persisted permanently — so storage only grows for funds people actually
look at, and every view after the first is a fast local query, never a
repeat external fetch. scheme_variants.nav_history_backfilled_at tracks
which variants have already been through this once.

Deliberately does not attempt to onboard new schemes or match by ISIN —
unlike the AMFI-file-based pipelines, this always starts from a
scheme_variant the caller already resolved (the one whose page is being
viewed), so there's no identity ambiguity to resolve here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.reference import SchemeVariant
from data_pipeline.sources.mfapi.client import MfApiFetchError, fetch_scheme_history
from data_pipeline.sources.mfapi.parser import parse_mfapi_history
from data_pipeline.storage.database_writer import get_or_create_data_source, write_nav_points

DATA_SOURCE_NAME = "api.mfapi.in (on-demand per-scheme backfill)"
DATA_SOURCE_URL = "https://api.mfapi.in"


@dataclass
class LazyBackfillOutcome:
    attempted: bool  # False if skipped (already backfilled, or no amfi_code to look up)
    success: bool = False
    inserted: int = 0
    skipped_points: int = 0
    error: str | None = None


def ensure_nav_history(db: Session, variant: SchemeVariant) -> LazyBackfillOutcome:
    """Backfill `variant`'s full NAV history from mfapi.in if it hasn't
    been done before. Safe to call on every fund-page request — a no-op
    (no network call) once nav_history_backfilled_at is set.

    Never raises: a failed attempt (network error, unknown scheme code,
    etc.) is reported in the returned outcome and leaves
    nav_history_backfilled_at unset so the next view retries, but the
    caller's request proceeds with whatever NAV history already exists
    (e.g. the daily feed's own points) rather than failing the page.
    """
    if variant.nav_history_backfilled_at is not None:
        return LazyBackfillOutcome(attempted=False)
    if not variant.amfi_code:
        return LazyBackfillOutcome(attempted=False)

    try:
        body = fetch_scheme_history(variant.amfi_code)
    except MfApiFetchError as exc:
        return LazyBackfillOutcome(attempted=True, success=False, error=str(exc))

    parsed = parse_mfapi_history(body)
    if not parsed.points:
        return LazyBackfillOutcome(attempted=True, success=False, error="no valid NAV points parsed")

    source = get_or_create_data_source(db, DATA_SOURCE_NAME, DATA_SOURCE_URL, "mfapi")
    db.commit()

    inserted = write_nav_points(db, source, variant.id, parsed.points)
    variant.nav_history_backfilled_at = datetime.now(timezone.utc)
    db.commit()

    return LazyBackfillOutcome(
        attempted=True, success=True, inserted=inserted, skipped_points=parsed.skipped
    )
