"""Daily fund-screener rollup: 1m/3m/6m/1y/3y/5y point-to-point returns
for every eligible scheme_variant, into fund_period_returns.

Design (see the plan this was agreed against): rather than storing a NAV
time series to compute these returns, each run fetches ONLY the exact NAV
points it needs — today's whole-universe snapshot, plus one snapshot per
lookback period's anchor date (data_pipeline/sources/amfi/
portal_history.py) — computes return_pct = nav_today / nav_anchor - 1 for
every eligible scheme directly from those two in-memory dicts, and
discards the snapshots once done. Nothing beyond the computed return
itself is persisted, so storage is bounded at
(eligible scheme count x 6 periods) regardless of how long this runs.

Eligible scope: Regular Plan + Growth option, AND Scheme.benchmark_id set
(see _eligible_variants). benchmark_id is only ever set by
benchmark_catalogue_sync.py, itself driven by AMFI's own real Equity
(investmentTypeList id=1) classification — so this is a real-data-backed
equity filter, not a guess at category text. Originally this filtered on
`classify_asset_class(category) != "Debt"`, which turned out to be far
too loose: real AMFI category strings include legacy "Income/Debt
Oriented Schemes - *" naming that doesn't start with the literal word
"Debt", so under the old filter only ~590 of ~1,727 "eligible" schemes
were actually Equity. daily_pipeline.py runs benchmark_catalogue_sync.py
before this module specifically so benchmark_id is fresh before this
filter runs.

Anchor dates are computed by calendar months (1/3/6/12/36/60 months back
from today), clamped to the target month's real last day when today's
day-of-month doesn't exist there (e.g. 31-Oct minus 1 month -> 30-Sep,
not an invalid 31-Sep) — see _months_before. A weekend/holiday anchor
date (no NAV published) steps back one day at a time, up to
_MAX_FALLBACK_DAYS, before being treated as genuinely unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reference import Scheme, SchemeVariant
from data_pipeline.sources.amfi.portal_history import (
    PortalHistoryFetchError,
    fetch_portal_history_for_date,
    parse_portal_history_navs,
)
from data_pipeline.storage.database_writer import get_or_create_data_source, write_period_returns

DATA_SOURCE_NAME = "AMFI Portal NAV History (fund screener daily rollup)"
DATA_SOURCE_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"

# (period key, months back) — the six windows the fund screener shows.
PERIODS: tuple[tuple[str, int], ...] = (
    ("1m", 1),
    ("3m", 3),
    ("6m", 6),
    ("1y", 12),
    ("3y", 36),
    ("5y", 60),
)

_MAX_FALLBACK_DAYS = 7
# On a non-trading day (weekend/market holiday), AMFI still publishes NAV
# for accrual-priced categories (Overnight/Liquid/debt ETFs — maybe ~600
# rows) even though equity and most debt funds have genuinely nothing
# that day — confirmed via a real live request for a real Saturday in
# this session. A full trading day's universe is ~8,000+ rows, so a
# response below this threshold is treated the same as empty (step back
# further) rather than accepted as "the real snapshot for this date" —
# otherwise a weekend/holiday anchor silently reports most schemes as
# DATA_UNAVAILABLE instead of falling back to the last real trading day.
_MIN_USABLE_ROW_COUNT = 1000


@dataclass
class RollupResult:
    eligible_variant_count: int
    as_of_date: date | None = None
    returns_computed: int = 0
    periods_unavailable: dict[str, int] | None = None  # period -> count of eligible schemes with no computable return
    fetch_errors: list[str] | None = None


def _months_before(d: date, months: int) -> date:
    """`d` minus `months` calendar months, clamping the day to the target
    month's real length (31-Oct minus 1 month -> 30-Sep, not 31-Sep)."""
    total_months = d.year * 12 + (d.month - 1) - months
    year, month0 = divmod(total_months, 12)
    month = month0 + 1
    # Days in `month` of `year`: first day of the NEXT month, minus one day.
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    days_in_month = (next_month_first - timedelta(days=1)).day
    return date(year, month, min(d.day, days_in_month))


def _eligible_variants(db: Session) -> dict[str, int]:
    """{amfi_code: scheme_variant_id} for Regular Plan + Growth option
    scheme_variants whose Scheme has a real, AMFI-confirmed benchmark_id
    (set only by benchmark_catalogue_sync.py, itself driven by AMFI's own
    Equity classification) — the fund screener's scope."""
    rows = db.execute(
        select(SchemeVariant.amfi_code, SchemeVariant.id)
        .join(Scheme, Scheme.id == SchemeVariant.scheme_id)
        .where(
            SchemeVariant.plan == "regular",
            SchemeVariant.option == "growth",
            SchemeVariant.amfi_code.is_not(None),
            Scheme.benchmark_id.is_not(None),
        )
    ).all()

    return {amfi_code: variant_id for amfi_code, variant_id in rows}


def _fetch_with_fallback(target_date: date) -> tuple[date, dict[str, float]] | None:
    """Try `target_date`, then step back one day at a time (weekends,
    market holidays have no published NAV) up to _MAX_FALLBACK_DAYS.
    Returns (actual_date_used, {scheme_code: nav}), or None if nothing
    was found within the fallback window."""
    for offset in range(_MAX_FALLBACK_DAYS + 1):
        attempt_date = target_date - timedelta(days=offset)
        try:
            raw = fetch_portal_history_for_date(attempt_date)
        except PortalHistoryFetchError:
            continue
        navs = parse_portal_history_navs(raw)
        if len(navs) >= _MIN_USABLE_ROW_COUNT:
            return attempt_date, navs
    return None


def run_period_return_rollup(db: Session, today: date | None = None) -> RollupResult:
    today = today or date.today()
    eligible = _eligible_variants(db)
    result = RollupResult(eligible_variant_count=len(eligible), as_of_date=today)
    if not eligible:
        return result

    fetch_errors: list[str] = []
    periods_unavailable: dict[str, int] = {}

    today_snapshot = _fetch_with_fallback(today)
    if today_snapshot is None:
        fetch_errors.append(f"Could not fetch today's ({today}) NAV snapshot within fallback window")
        result.fetch_errors = fetch_errors
        return result
    today_actual_date, today_navs = today_snapshot

    source = get_or_create_data_source(db, DATA_SOURCE_NAME, DATA_SOURCE_URL, "amfi")
    rows: list[dict] = []

    for period, months_back in PERIODS:
        anchor_target = _months_before(today, months_back)
        anchor_snapshot = _fetch_with_fallback(anchor_target)
        if anchor_snapshot is None:
            fetch_errors.append(f"Could not fetch {period} anchor ({anchor_target}) NAV snapshot within fallback window")
            periods_unavailable[period] = len(eligible)
            continue
        anchor_actual_date, anchor_navs = anchor_snapshot

        missing_for_period = 0
        for amfi_code, variant_id in eligible.items():
            nav_today = today_navs.get(amfi_code)
            nav_anchor = anchor_navs.get(amfi_code)
            if nav_today is None or nav_anchor is None or nav_anchor <= 0:
                missing_for_period += 1
                continue
            rows.append(
                {
                    "scheme_variant_id": variant_id,
                    "period": period,
                    "return_pct": round((nav_today / nav_anchor - 1) * 100, 4),
                    "as_of_date": today_actual_date,
                    "anchor_date": anchor_actual_date,
                }
            )
        if missing_for_period:
            periods_unavailable[period] = missing_for_period

    result.returns_computed = write_period_returns(db, source, rows)
    db.commit()
    result.periods_unavailable = periods_unavailable
    result.fetch_errors = fetch_errors or None
    return result
