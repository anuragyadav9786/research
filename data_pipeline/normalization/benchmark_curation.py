"""Manual fund/category -> benchmark curation.

Neither AMFI's NAVAll.txt nor the portfolio-disclosure pipeline
(portfolio-fetcher/) states which index a real scheme benchmarks against
(confirmed by reading both — see docs/data-sources.md's benchmark-mapping
note), so `Scheme.benchmark_id` is never set for a real onboarded scheme
(scheme_onboarding.py inserts every Scheme with benchmark_id left NULL).
This module closes that gap with a human-verified mapping instead of
guessing one from category alone — get_effective_benchmark_id's own
docstring is explicit that a benchmark is "never guessed from its
category" by that function; this module is the deliberate, human-supplied
answer that function then reads, not an automated inference.

Two levels, checked in this order per scheme:

1. SCHEME_BENCHMARK_OVERRIDES — keyed by exact Scheme.name, for a specific
   fund whose benchmark was confirmed from its own factsheet (can differ
   from its category's usual benchmark).
2. CATEGORY_BENCHMARK_MAP — keyed by the exact AMFI category string
   (Scheme.category, e.g. "Equity Scheme - Large Cap Fund"), the
   conventional benchmark for that category.

Both are intentionally empty until filled in with sourced entries — never
pre-populated with a guessed index name here.

Only an NSE-fetchable TRI index (provider="NSE", symbol matching the exact
name NSE's endpoint expects, e.g. "NIFTY 50 TRI") gets live-computed
CAGR/drawdown/volatility figures today (see
data_pipeline/sources/benchmarks/registry.py) — a BSE/CRISIL/MSCI
benchmark can still be named here (benchmark_name shows up in the UI) but
its figures stay unavailable until one of those providers is built.

Never overwrites a scheme that already has a benchmark assigned, whether
via `scheme.benchmark_id` or any existing `fund_benchmark_history` row
(open or historical) — this only fills genuine gaps.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.reference import Benchmark, FundBenchmarkHistory, Scheme


@dataclass(frozen=True)
class BenchmarkSpec:
    name: str
    index_code: str | None = None
    provider: str | None = None  # "NSE" if fetchable via data_pipeline/sources/benchmarks/nse.py
    symbol: str | None = None  # the exact index name NSE's endpoint expects, if provider == "NSE"
    benchmark_type: str | None = None  # "TRI" or "PRICE"


# Keyed by the exact AMFI category string (Scheme.category). Fill in as
# categories are confirmed.
CATEGORY_BENCHMARK_MAP: dict[str, BenchmarkSpec] = {}

# Keyed by exact Scheme.name, confirmed from that scheme's own factsheet.
# Takes priority over CATEGORY_BENCHMARK_MAP.
SCHEME_BENCHMARK_OVERRIDES: dict[str, BenchmarkSpec] = {}


@dataclass
class CurationResult:
    benchmarks_created: int = 0
    schemes_assigned: int = 0
    schemes_skipped_already_mapped: int = 0
    schemes_skipped_no_mapping: int = 0
    assigned_scheme_names: list[str] = field(default_factory=list)


def _get_or_create_benchmark(db: Session, spec: BenchmarkSpec, cache: dict[str, Benchmark]) -> tuple[Benchmark, bool]:
    cached = cache.get(spec.name)
    if cached is not None:
        return cached, False

    existing = db.query(Benchmark).filter(Benchmark.name == spec.name).first()
    if existing is not None:
        cache[spec.name] = existing
        return existing, False

    benchmark = Benchmark(
        name=spec.name,
        index_code=spec.index_code,
        provider=spec.provider,
        symbol=spec.symbol,
        benchmark_type=spec.benchmark_type,
    )
    db.add(benchmark)
    db.flush()
    cache[spec.name] = benchmark
    return benchmark, True


def apply_manual_benchmark_curation(db: Session) -> CurationResult:
    result = CurationResult()
    if not CATEGORY_BENCHMARK_MAP and not SCHEME_BENCHMARK_OVERRIDES:
        return result

    benchmark_cache: dict[str, Benchmark] = {}
    already_mapped_scheme_ids = {
        row.scheme_id for row in db.query(FundBenchmarkHistory.scheme_id).distinct().all()
    }

    for scheme in db.query(Scheme).all():
        if scheme.benchmark_id is not None or scheme.id in already_mapped_scheme_ids:
            result.schemes_skipped_already_mapped += 1
            continue

        spec = SCHEME_BENCHMARK_OVERRIDES.get(scheme.name) or CATEGORY_BENCHMARK_MAP.get(scheme.category)
        if spec is None:
            result.schemes_skipped_no_mapping += 1
            continue

        benchmark, created = _get_or_create_benchmark(db, spec, benchmark_cache)
        if created:
            result.benchmarks_created += 1

        scheme.benchmark_id = benchmark.id
        db.add(
            FundBenchmarkHistory(
                scheme_id=scheme.id,
                benchmark_id=benchmark.id,
                start_date=None,
                end_date=None,
                source="manual_curation",
            )
        )
        result.schemes_assigned += 1
        result.assigned_scheme_names.append(scheme.name)

    db.commit()
    return result
