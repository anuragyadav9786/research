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

GAP REPAIR (added after a real production bug): nav_history_backfilled_at
being set was assumed to mean "this variant's history is complete
forever," but a real fund (HDFC Flexi Cap Fund, Direct Growth) was found
with a genuine 1,095-day hole in the middle of its NAV history despite
the flag being set — confirmed live that mfapi.in's OWN data has no such
gap (a fresh fetch returns the missing rows), so this was a one-time
write/retry issue, not an upstream data problem, and the one-time flag
meant nothing would ever revisit it. ensure_nav_history now also runs a
cheap local gap check (one indexed query, no network) on every view of an
already-backfilled variant, and re-fetches mfapi.in's full history to
repair a real gap — ON CONFLICT DO NOTHING (write_nav_points) makes
re-writing already-correct rows a safe no-op, so this only ever fills
what's actually missing. Gated by nav_gap_repair_attempted_at so a
genuinely permanent gap costs one wasted mfapi.in call per
_GAP_RECHECK_COOLDOWN_DAYS, not one per page view forever.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.reference import SchemeVariant
from data_pipeline.sources.mfapi.client import MfApiFetchError, fetch_scheme_history
from data_pipeline.sources.mfapi.parser import parse_mfapi_history
from data_pipeline.storage.database_writer import get_or_create_data_source, write_nav_points

DATA_SOURCE_NAME = "api.mfapi.in (on-demand per-scheme backfill)"
DATA_SOURCE_URL = "https://api.mfapi.in"

# Even India's longest market-holiday clusters (e.g. a long Diwali/New
# Year stretch) run well under this many days — a real gap this large
# means data is missing, not that the market was closed. Picked well
# above any legitimate holiday run to avoid false positives.
_GAP_THRESHOLD_DAYS = 20
# Don't re-hit mfapi.in on every single page view for a gap that didn't
# close last time (e.g. a genuinely delisted/merged scheme) — one wasted
# call per cooldown window, not one per visitor.
_GAP_RECHECK_COOLDOWN_DAYS = 7


@dataclass
class LazyBackfillOutcome:
    attempted: bool  # False if skipped (already backfilled, or no amfi_code to look up)
    success: bool = False
    inserted: int = 0
    skipped_points: int = 0
    error: str | None = None


def _max_nav_gap_days(db: Session, variant_id: int) -> int | None:
    """Largest gap, in days, between two consecutive nav_history dates for
    this variant — a single indexed query, no network, safe to run on
    every view. None if there are fewer than 2 rows (nothing to compare)."""
    return db.execute(
        text(
            """
            SELECT max(gap_days) FROM (
                SELECT date - lag(date) OVER (ORDER BY date) AS gap_days
                FROM nav_history WHERE scheme_variant_id = :vid
            ) sub
            """
        ),
        {"vid": variant_id},
    ).scalar()


def _fetch_and_write(db: Session, variant: SchemeVariant) -> LazyBackfillOutcome:
    """Shared fetch -> parse -> write for both the first-time backfill and
    a later gap repair — identical mfapi.in call either way (it always
    returns the scheme's entire history), just a different caller-side
    decision about when to make it."""
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
    return LazyBackfillOutcome(attempted=True, success=True, inserted=inserted, skipped_points=parsed.skipped)


def ensure_nav_history(db: Session, variant: SchemeVariant) -> LazyBackfillOutcome:
    """Backfill `variant`'s full NAV history from mfapi.in if it hasn't
    been done before, or repair a real gap in an already-backfilled
    variant's history (see module docstring). Safe to call on every
    fund-page request — a no-op (no network call) once backfilled and gap
    -free, or while a repair attempt is still within its cooldown window.

    Never raises: a failed attempt (network error, unknown scheme code,
    etc.) is reported in the returned outcome, but the caller's request
    proceeds with whatever NAV history already exists rather than failing
    the page.
    """
    if not variant.amfi_code:
        return LazyBackfillOutcome(attempted=False)

    if variant.nav_history_backfilled_at is None:
        outcome = _fetch_and_write(db, variant)
        if outcome.success:
            variant.nav_history_backfilled_at = datetime.now(timezone.utc)
        db.commit()
        return outcome

    if variant.nav_gap_repair_attempted_at is not None:
        cooldown_elapsed = datetime.now(timezone.utc) - variant.nav_gap_repair_attempted_at
        if cooldown_elapsed < timedelta(days=_GAP_RECHECK_COOLDOWN_DAYS):
            return LazyBackfillOutcome(attempted=False)

    max_gap = _max_nav_gap_days(db, variant.id)
    if max_gap is None or max_gap <= _GAP_THRESHOLD_DAYS:
        return LazyBackfillOutcome(attempted=False)

    outcome = _fetch_and_write(db, variant)
    variant.nav_gap_repair_attempted_at = datetime.now(timezone.utc)
    db.commit()
    return outcome
