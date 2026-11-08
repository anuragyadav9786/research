"""Read-only data access for cross-fund security lookup — "which schemes
hold this stock/bond" — the reverse direction of
portfolio_repository.get_holdings (scheme -> its securities).

Security has no ORM relationship to Sector defined (same reason
portfolio_repository.py joins it explicitly rather than adding one just
for these reads).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.reference import AMC, FundFamily, Scheme, Sector, Security
from app.models.timeseries import PortfolioHolding, PortfolioSnapshot

SEARCH_RESULT_LIMIT = 20


@dataclass
class HolderRow:
    scheme_id: int
    scheme_name: str
    amc_name: str
    as_of_date: date
    weight_pct: float
    market_value: float | None


def search_securities(db: Session, query: str, limit: int = SEARCH_RESULT_LIMIT) -> list[Security]:
    return (
        db.query(Security)
        .filter(or_(Security.name.ilike(f"%{query}%"), Security.isin.ilike(f"%{query}%")))
        .order_by(Security.name)
        .limit(limit)
        .all()
    )


def get_security(db: Session, security_id: int) -> Security | None:
    return db.get(Security, security_id)


def get_security_sector_name(db: Session, security: Security) -> str | None:
    if security.sector_id is None:
        return None
    sector = db.get(Sector, security.sector_id)
    return sector.name if sector else None


def get_holders(db: Session, security_id: int) -> list[HolderRow]:
    # Only each scheme's latest disclosure date for this security — a
    # scheme that held it last month but no longer does shouldn't show up
    # as a current holder. Written as a per-scheme max-date join (not
    # assumed to be exactly one snapshot per scheme) so this already
    # generalizes once a second month's disclosure exists.
    latest_dates = (
        db.query(PortfolioSnapshot.scheme_id, func.max(PortfolioSnapshot.as_of_date).label("max_date"))
        .join(PortfolioHolding, PortfolioHolding.snapshot_id == PortfolioSnapshot.id)
        .filter(PortfolioHolding.security_id == security_id)
        .group_by(PortfolioSnapshot.scheme_id)
        .subquery()
    )

    rows = (
        db.query(PortfolioHolding, PortfolioSnapshot, Scheme, AMC)
        .join(PortfolioSnapshot, PortfolioHolding.snapshot_id == PortfolioSnapshot.id)
        .join(
            latest_dates,
            (PortfolioSnapshot.scheme_id == latest_dates.c.scheme_id)
            & (PortfolioSnapshot.as_of_date == latest_dates.c.max_date),
        )
        .join(Scheme, PortfolioSnapshot.scheme_id == Scheme.id)
        .join(FundFamily, Scheme.fund_family_id == FundFamily.id)
        .join(AMC, FundFamily.amc_id == AMC.id)
        .filter(PortfolioHolding.security_id == security_id)
        .order_by(PortfolioHolding.weight_pct.desc())
        .all()
    )

    return [
        HolderRow(
            scheme_id=scheme.id,
            scheme_name=scheme.name,
            amc_name=amc.name,
            as_of_date=snapshot.as_of_date,
            weight_pct=float(holding.weight_pct),
            market_value=float(holding.market_value) if holding.market_value is not None else None,
        )
        for holding, snapshot, scheme, amc in rows
    ]
