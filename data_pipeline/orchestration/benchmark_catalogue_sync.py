"""Backfills Scheme.benchmark_id for real Equity schemes from AMFI's own
disclosed benchmark (data_pipeline/sources/amfi/fund_performance.py) —
replaces the old manual category->benchmark guessing
(benchmark_curation.py's CATEGORY_BENCHMARK_MAP) with the AMC's own
stated benchmark, scheme by scheme, for every real sub-category AMFI
itself defines (not a hardcoded list — fetched fresh each run via
fetch_subcategories, so a new AMFI sub-category is picked up
automatically).

This is a catalogue sync, not a history backfill: it only creates/updates
`benchmarks` rows (by name) and sets `schemes.benchmark_id` — it never
touches `benchmark_history`. Which indices actually need their TRI
history fetched is a separate, deliberately later decision (see
docs/data-sources.md and this session's own discussion): only the
distinct benchmark names this sync actually assigns to a real scheme,
never a blanket fetch of every index AMFI/NSE/BSE knows about.

Scheme matching is by normalized name (casefold + whitespace-collapsed)
against this platform's own Scheme.name — both ultimately trace back to
AMFI as the source of truth for a scheme's bare name (see parser.py's
module docstring), so this should match cleanly for most real schemes.
An unmatched AMFI scheme name is reported, never silently dropped or
fuzzy-guessed into the wrong scheme.

Real production bug found and fixed via this session's own live probes:
the very first two production runs of this sync (one right after it
shipped, one right after the BSE override below shipped) both silently
matched zero schemes -- not a fetch error, but AMFI returning
validationStatus=SUCCESS with an empty `data` list for every
sub-category. A live probe confirmed why: AMFI's fund-performance report
for "today" (and even "yesterday") isn't published yet -- a ~2-day
publication lag, consistent across sub-categories. See
_resolve_report_date: it steps back day by day (bounded by
_MAX_REPORT_DATE_FALLBACK_DAYS), the same pattern
period_return_rollup.py already uses for its own AMFI endpoint, and the
actual date used is reported back on the result as report_date_used so
this is never silently wrong again.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.reference import Benchmark, Scheme
from data_pipeline.sources.amfi.fund_performance import (
    INVESTMENT_TYPE_EQUITY,
    FundPerformanceFetchError,
    SubCategory,
    fetch_scheme_performance,
    fetch_subcategories,
)

# AMFI's fund-performance report for a given calendar date isn't published
# immediately -- confirmed via a real live probe this session: on
# 21-Oct-2026, both 21-Oct and 20-Oct returned SUCCESS with zero rows for
# every real sub-category, while 19-Oct returned real data -- a ~2-day
# lag, not a fetch failure (no exception, just an empty `data` list). A
# sub-category's data becomes available in step with every other
# sub-category's (confirmed the same real lag across 3 real sub-categories
# this session), so resolving the latest usable date against just the
# first sub-category is representative of the whole run. Mirrors the same
# step-back-a-day pattern period_return_rollup.py already uses for its own
# AMFI endpoint, for the same reason (today's data may not exist yet).
_MAX_REPORT_DATE_FALLBACK_DAYS = 7


def _resolve_report_date(target_date: date, probe_subcategory: SubCategory) -> date | None:
    for offset in range(_MAX_REPORT_DATE_FALLBACK_DAYS + 1):
        attempt_date = target_date - timedelta(days=offset)
        try:
            rows = fetch_scheme_performance(
                INVESTMENT_TYPE_EQUITY, probe_subcategory.id, attempt_date.strftime("%d-%b-%Y")
            )
        except FundPerformanceFetchError:
            continue
        if rows:
            return attempt_date
    return None

_NSE_PREFIX = ("nifty",)
_BSE_PREFIX = ("bse", "s&p bse")

# Deliberate, explicit, user-approved TEMPORARY override: this platform
# has a confirmed-working TRI data source for NSE/Nifty-branded indices
# (niftyindices.com) but none yet for BSE-branded ones. Nifty and BSE
# indices are correlated but NOT the same instrument (different
# constituent selection/weighting/rebalancing) — substituting one for the
# other is a real approximation, not a neutral relabeling, so it is only
# applied to a small, explicit table of pairs rather than any mechanical
# name transform. Every pair here was seen in real AMFI fundperformance
# data this session (e.g. "BSE 100 TRI" disclosed for several real Large
# Cap schemes alongside "Nifty 100 TRI" for others in the same
# sub-category). A BSE-branded benchmark NOT in this table is left
# unmatched (reported, benchmark_id not set) rather than guessed at —
# extend this table only once a specific pair is itself confirmed.
_BSE_TO_NIFTY_OVERRIDE: dict[str, str] = {
    "BSE 100 TRI": "Nifty 100 TRI",
    "BSE 500 TRI": "Nifty 500 TRI",
}


def _normalize(name: str) -> str:
    return " ".join(name.casefold().split())


def _provider_for(benchmark_name: str) -> str | None:
    normalized = benchmark_name.casefold()
    if normalized.startswith(_NSE_PREFIX):
        return "NSE"
    if normalized.startswith(_BSE_PREFIX):
        return "BSE"
    return None


def _benchmark_type_for(benchmark_name: str) -> str:
    return "TRI" if "tri" in benchmark_name.casefold() else "PRICE"


@dataclass
class CatalogueSyncResult:
    subcategories_processed: int = 0
    schemes_seen: int = 0
    schemes_matched: int = 0
    schemes_unmatched: list[str] = field(default_factory=list)
    benchmarks_created: int = 0
    # {benchmark_name: provider ("NSE" / "BSE" / None)} for every distinct
    # benchmark actually assigned to a real matched scheme this run — the
    # real, bounded "what do we actually need to backfill" list.
    distinct_benchmarks_assigned: dict[str, str | None] = field(default_factory=dict)
    fetch_errors: list[str] = field(default_factory=list)
    # The real report date AMFI actually had data for -- may be a few days
    # before the requested one (see _resolve_report_date). None if no
    # usable date was found at all within the fallback window.
    report_date_used: date | None = None


def run_benchmark_catalogue_sync(db: Session, report_date: date | None = None) -> CatalogueSyncResult:
    requested_date = report_date or date.today()
    result = CatalogueSyncResult()

    schemes_by_normalized_name = {_normalize(s.name): s for s in db.query(Scheme).all()}
    benchmark_by_name: dict[str, Benchmark] = {b.name: b for b in db.query(Benchmark).all()}

    try:
        subcategories = fetch_subcategories(INVESTMENT_TYPE_EQUITY)
    except FundPerformanceFetchError as exc:
        result.fetch_errors.append(f"Could not fetch Equity sub-category list: {exc}")
        return result
    if not subcategories:
        result.fetch_errors.append("AMFI returned no Equity sub-categories")
        return result

    resolved_date = _resolve_report_date(requested_date, subcategories[0])
    if resolved_date is None:
        result.fetch_errors.append(
            f"No AMFI fund-performance report had data within {_MAX_REPORT_DATE_FALLBACK_DAYS} days of {requested_date}"
        )
        return result
    result.report_date_used = resolved_date
    report_date_str = resolved_date.strftime("%d-%b-%Y")

    for sub in subcategories:
        result.subcategories_processed += 1
        try:
            rows = fetch_scheme_performance(INVESTMENT_TYPE_EQUITY, sub.id, report_date_str)
        except FundPerformanceFetchError as exc:
            result.fetch_errors.append(f"Could not fetch '{sub.name}' (id={sub.id}): {exc}")
            continue

        for row in rows:
            result.schemes_seen += 1
            if not row.benchmark:
                result.schemes_unmatched.append(f"{row.scheme_name} (no benchmark disclosed)")
                continue

            scheme = schemes_by_normalized_name.get(_normalize(row.scheme_name))
            if scheme is None:
                result.schemes_unmatched.append(row.scheme_name)
                continue

            # Apply the explicit, user-approved BSE->Nifty override (see
            # _BSE_TO_NIFTY_OVERRIDE above) before matching/creating the
            # Benchmark row. A BSE-branded name with no confirmed Nifty
            # equivalent is left unmatched rather than assigned a BSE-only
            # Benchmark row we have no TRI history source for.
            effective_name = row.benchmark
            if effective_name in _BSE_TO_NIFTY_OVERRIDE:
                effective_name = _BSE_TO_NIFTY_OVERRIDE[effective_name]
            elif effective_name.casefold().startswith(_BSE_PREFIX):
                result.schemes_unmatched.append(
                    f"{row.scheme_name} (BSE-benchmarked '{row.benchmark}', no confirmed Nifty equivalent yet)"
                )
                continue

            benchmark = benchmark_by_name.get(effective_name)
            if benchmark is None:
                benchmark = Benchmark(
                    name=effective_name,
                    provider=_provider_for(effective_name),
                    symbol=effective_name,
                    benchmark_type=_benchmark_type_for(effective_name),
                )
                db.add(benchmark)
                db.flush()
                benchmark_by_name[effective_name] = benchmark
                result.benchmarks_created += 1

            scheme.benchmark_id = benchmark.id
            result.schemes_matched += 1
            result.distinct_benchmarks_assigned[effective_name] = benchmark.provider

    db.commit()
    return result
