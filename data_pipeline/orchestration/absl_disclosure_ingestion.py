"""Writes parsed ABSL monthly portfolio-disclosure data
(absl_disclosure_parser.py's `DisclosureScheme`/`DisclosureHolding`)
into `portfolio_snapshots`/`portfolio_holdings`/`securities` -- the
ingestion half of the pipeline `portfolio-fetcher/README.md` promises
but that, until now, didn't exist anywhere in this repo (confirmed:
`portfolio-fetcher/` only uploads the raw file to Google Drive).

Scheme identity is resolved via `absl_scheme_identity.py`'s curated
short_code -> Scheme.name table -- a scheme not yet in that table is
reported as unmapped and its entire sheet is skipped, never guessed.

Security identity is resolved by ISIN (get-or-create, the same
never-fuzzy-match discipline `cas_service.py` already uses for investor
CAS holdings) for a real security, or by `(isin IS NULL, name)` for a
cash-equivalent/TREPS/margin/other-current-asset row that has none -- a
small, fixed vocabulary of real names this file actually uses (e.g.
"TREPS", "Net Receivable / Payable"), so the same row is reused across
every scheme/month rather than duplicated once per occurrence.

An existing Security's `sector_id`/`instrument_type` are only ever
*filled in* when currently NULL, never overwritten -- the same
conservative "never overwrite an existing classification" rule
`benchmark_curation.py` already applies to `Scheme.benchmark_id`, in
case an earlier source's classification disagrees with this one.
`market_cap_category` is never touched here -- this file doesn't state
it.

Idempotent per (scheme, as_of_date): re-running for a month already
ingested deletes and rewrites that one snapshot's holdings rather than
accumulating duplicates -- the same "deliberately overwrite" convention
`precompute_metrics.py` already uses for its own monthly-rollup table.
"""
from __future__ import annotations

from datetime import date
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.reference import Scheme, Sector, Security
from app.models.timeseries import PortfolioHolding, PortfolioSnapshot
from data_pipeline.normalization.absl_disclosure_parser import DisclosureHolding, DisclosureScheme
from data_pipeline.normalization.absl_scheme_identity import resolve_scheme_for_short_code
from data_pipeline.storage.database_writer import get_or_create_data_source

DATA_SOURCE_NAME = "ABSL Monthly Portfolio Disclosure"
DATA_SOURCE_URL = "https://mutualfund.adityabirlacapital.com"


@dataclass
class IngestionResult:
    schemes_written: int = 0
    holdings_written: int = 0
    securities_created: int = 0
    sectors_created: int = 0
    schemes_skipped_unmapped: list[str] = field(default_factory=list)


def ingest_absl_disclosure(db: Session, amc_name: str, schemes: list[DisclosureScheme]) -> IngestionResult:
    """Writes every scheme `absl_disclosure_parser.parse_disclosure_workbook`
    produced, for whichever ones `amc_name` + `absl_scheme_identity`'s
    curated table can actually resolve to an onboarded `Scheme`. Commits
    once at the end -- a partial, uncommitted write on an exception
    leaves the database exactly as it was before this call, never a
    half-ingested month."""
    result = IngestionResult()
    source = get_or_create_data_source(db, name=DATA_SOURCE_NAME, url=DATA_SOURCE_URL, source_type="amc")
    security_cache: dict[tuple[str | None, str], Security] = {}
    sector_cache: dict[str, Sector] = {}

    for disclosure_scheme in schemes:
        scheme = resolve_scheme_for_short_code(db, amc_name, disclosure_scheme.short_code)
        if scheme is None:
            result.schemes_skipped_unmapped.append(disclosure_scheme.short_code)
            continue

        snapshot = _get_or_replace_snapshot(db, scheme.id, disclosure_scheme.as_of_date, source.id)
        for holding in disclosure_scheme.holdings:
            security, created = _get_or_create_security(db, holding, security_cache, sector_cache, result)
            if created:
                result.securities_created += 1
            db.add(
                PortfolioHolding(
                    snapshot_id=snapshot.id,
                    security_id=security.id,
                    weight_pct=round(holding.weight_pct, 3),
                    market_value=round(holding.market_value_rupees, 2),
                    quantity=round(holding.quantity, 4) if holding.quantity is not None else None,
                    credit_rating=holding.credit_rating,
                    ytm_pct=round(holding.ytm_pct, 3) if holding.ytm_pct is not None else None,
                    ytc_pct=round(holding.ytc_pct, 3) if holding.ytc_pct is not None else None,
                )
            )
            result.holdings_written += 1
        result.schemes_written += 1

    db.commit()
    return result


def _get_or_replace_snapshot(db: Session, scheme_id: int, as_of_date: date, source_id: int) -> PortfolioSnapshot:
    existing = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.scheme_id == scheme_id, PortfolioSnapshot.as_of_date == as_of_date)
        .first()
    )
    if existing is not None:
        db.query(PortfolioHolding).filter(PortfolioHolding.snapshot_id == existing.id).delete()
        existing.source_id = source_id
        db.flush()
        return existing

    snapshot = PortfolioSnapshot(scheme_id=scheme_id, as_of_date=as_of_date, source_id=source_id)
    db.add(snapshot)
    db.flush()
    return snapshot


def _get_or_create_sector(db: Session, name: str, cache: dict[str, Sector], result: IngestionResult) -> Sector:
    cached = cache.get(name)
    if cached is not None:
        return cached
    existing = db.query(Sector).filter(Sector.name == name).first()
    if existing is not None:
        cache[name] = existing
        return existing
    sector = Sector(name=name)
    db.add(sector)
    db.flush()
    cache[name] = sector
    result.sectors_created += 1
    return sector


def _get_or_create_security(
    db: Session,
    holding: DisclosureHolding,
    security_cache: dict[tuple[str | None, str], Security],
    sector_cache: dict[str, Sector],
    result: IngestionResult,
) -> tuple[Security, bool]:
    cache_key = (holding.isin, holding.instrument_name if holding.isin is None else "")
    cached = security_cache.get(cache_key)
    if cached is not None:
        return cached, False

    query = db.query(Security)
    query = (
        query.filter(Security.isin == holding.isin)
        if holding.isin is not None
        else query.filter(Security.isin.is_(None), Security.name == holding.instrument_name)
    )
    existing = query.first()
    if existing is not None:
        # Fill in a classification this security is still missing -- never
        # overwrite one it already has, in case an earlier source's
        # classification disagrees with this one.
        if existing.instrument_type is None:
            existing.instrument_type = holding.instrument_type
        if existing.sector_id is None and holding.sector is not None:
            existing.sector_id = _get_or_create_sector(db, holding.sector, sector_cache, result).id
        security_cache[cache_key] = existing
        return existing, False

    sector_id = _get_or_create_sector(db, holding.sector, sector_cache, result).id if holding.sector else None
    security = Security(
        isin=holding.isin,
        name=holding.instrument_name,
        instrument_type=holding.instrument_type,
        sector_id=sector_id,
    )
    db.add(security)
    db.flush()
    security_cache[cache_key] = security
    return security, True
