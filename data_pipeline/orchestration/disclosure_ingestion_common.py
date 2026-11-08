"""Shared, AMC-agnostic core of every monthly portfolio-disclosure
ingestion job: resolves/creates Security and Sector rows, replaces a
scheme's snapshot idempotently, and writes PortfolioHolding rows -- all
driven by the canonical DisclosureScheme/DisclosureHolding shapes
(data_pipeline/normalization/disclosure_types.py) rather than anything
AMC-specific.

Extracted out of absl_disclosure_ingestion.py once a second real AMC
adapter (Motilal Oswal) existed to prove the shape stays AMC-agnostic --
deliberately not built before that, since designing it against one
example risks baking in assumptions nothing but a second real example can
actually test.

Security resolution is ISIN-first get-or-create (never fuzzy-matched),
the same discipline cas_service.py already uses. It was already safe to
re-run for a second AMC without duplicating a security an earlier AMC's
disclosure already created -- the original per-row version issued one
SELECT per holding even when that holding's ISIN definitely already
existed. This module fixes that: `_prefetch_securities`/`_prefetch_sectors`
load every ISIN/sector this run will touch in one query each (chunked,
mirroring database_writer.py's own _INSERT_BATCH_SIZE precedent) before
the per-scheme loop starts, so a cache miss there means "genuinely new,"
not "not looked up yet."

Sector-name matching is still exact-string (after folding incidental
whitespace/case, not a synonym table) -- a genuine wording difference
between AMCs (e.g. "Banking" vs "Banks") stays two distinct Sector rows
on purpose; building a canonical cross-AMC synonym table now, before any
real AMC pair has shown what divergence actually exists, would be
guessing.
"""
from __future__ import annotations

from datetime import date
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from app.models.reference import Scheme, Sector, Security
from app.models.timeseries import PortfolioHolding, PortfolioSnapshot
from data_pipeline.normalization.disclosure_types import DisclosureHolding, DisclosureScheme
from data_pipeline.storage.database_writer import get_or_create_data_source

# Same rationale as database_writer._INSERT_BATCH_SIZE: Postgres caps a
# single statement's bind parameters, and an oversized IN-list risks the
# same "SSL connection closed" failure mode a real over-sized call hit
# there. A single AMC's monthly file is nowhere near this (ABSL's real
# September 2026 file had ~1,900 distinct ISINs), but chunking costs
# nothing when under the limit and avoids ever needing to revisit this.
_PREFETCH_CHUNK_SIZE = 5000

SchemeResolver = Callable[[Session, str, str], "Scheme | None"]


@dataclass
class IngestionResult:
    schemes_written: int = 0
    holdings_written: int = 0
    securities_created: int = 0
    sectors_created: int = 0
    schemes_skipped_unmapped: list[str] = field(default_factory=list)


def ingest_amc_disclosure(
    db: Session,
    amc_name: str,
    data_source_name: str,
    data_source_url: str,
    schemes: list[DisclosureScheme],
    scheme_resolver: SchemeResolver,
) -> IngestionResult:
    """Writes every scheme a disclosure parser produced, for whichever
    ones `amc_name` + `scheme_resolver` can actually resolve to an
    onboarded `Scheme`. Commits once at the end -- a partial, uncommitted
    write on an exception leaves the database exactly as it was before
    this call, never a half-ingested month."""
    result = IngestionResult()
    source = get_or_create_data_source(db, name=data_source_name, url=data_source_url, source_type="amc")

    all_holdings = [holding for scheme in schemes for holding in scheme.holdings]
    security_cache = _prefetch_securities(db, all_holdings)
    sector_cache = _prefetch_sectors(db)

    for disclosure_scheme in schemes:
        scheme = scheme_resolver(db, amc_name, disclosure_scheme.short_code)
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


def _prefetch_securities(
    db: Session, holdings: list[DisclosureHolding]
) -> dict[tuple[str | None, str], Security]:
    """Every Security this run could possibly match, loaded up front so
    the per-holding loop's cache miss always means "genuinely new."
    Mirrors _get_or_create_security's own cache-key shape: ISIN-keyed
    securities under `(isin, "")`, null-ISIN ones under `(None, name)`."""
    isins = sorted({h.isin for h in holdings if h.isin is not None})
    null_isin_names = sorted({h.instrument_name for h in holdings if h.isin is None})
    cache: dict[tuple[str | None, str], Security] = {}

    for i in range(0, len(isins), _PREFETCH_CHUNK_SIZE):
        chunk = isins[i : i + _PREFETCH_CHUNK_SIZE]
        for security in db.query(Security).filter(Security.isin.in_(chunk)):
            cache[(security.isin, "")] = security

    for i in range(0, len(null_isin_names), _PREFETCH_CHUNK_SIZE):
        chunk = null_isin_names[i : i + _PREFETCH_CHUNK_SIZE]
        for security in db.query(Security).filter(Security.isin.is_(None), Security.name.in_(chunk)):
            cache[(None, security.name)] = security

    return cache


def _normalize_sector_key(name: str) -> str:
    """Folds incidental formatting variance only (whitespace, case) --
    NOT a synonym table. "Banking" vs "Banks" is a real wording
    difference and stays two rows; see module docstring."""
    return " ".join(name.split()).casefold()


def _prefetch_sectors(db: Session) -> dict[str, Sector]:
    """Sector is a small, bounded reference table (tens to a few hundred
    rows, AMFI-style taxonomy) -- prefetch the whole thing once per run
    rather than an IN-list keyed to this run's own category labels."""
    return {_normalize_sector_key(sector.name): sector for sector in db.query(Sector).all()}


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
    key = _normalize_sector_key(name)
    cached = cache.get(key)
    if cached is not None:
        return cached
    sector = Sector(name=name)
    db.add(sector)
    db.flush()
    cache[key] = sector
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
        # A cache hit after the up-front prefetch means "genuinely seen
        # before in this run" -- either pre-existing (and possibly
        # missing a classification to fill in) or just created earlier
        # in this same run (already fully classified, nothing to do).
        if cached.instrument_type is None:
            cached.instrument_type = holding.instrument_type
        if cached.sector_id is None and holding.sector is not None:
            cached.sector_id = _get_or_create_sector(db, holding.sector, sector_cache, result).id
        return cached, False

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
