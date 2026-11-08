"""Read-only data access for browsing AMCs and their schemes — the
AMC-level equivalent of fund_repository.py's scheme-level queries. AMC
has never had its own browsing surface before (only a free-text filter
on scheme search), so there's nothing existing to extend here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.reference import AMC, FundFamily, Scheme
from app.models.timeseries import PortfolioSnapshot


@dataclass
class AmcSummaryRow:
    id: int
    name: str
    fund_family_count: int
    scheme_count: int
    schemes_with_holdings_count: int


@dataclass
class AmcSchemeRow:
    id: int
    scheme_name: str
    category: str
    fund_family_name: str
    benchmark_name: str | None
    holdings_as_of_date: date | None


def list_amcs(db: Session) -> list[AmcSummaryRow]:
    amcs = db.query(AMC).order_by(AMC.name).all()
    if not amcs:
        return []

    fund_family_counts = dict(
        db.query(AMC.id, func.count(FundFamily.id)).join(FundFamily, FundFamily.amc_id == AMC.id).group_by(AMC.id).all()
    )
    scheme_counts = dict(
        db.query(AMC.id, func.count(Scheme.id))
        .join(FundFamily, FundFamily.amc_id == AMC.id)
        .join(Scheme, Scheme.fund_family_id == FundFamily.id)
        .group_by(AMC.id)
        .all()
    )
    holdings_counts = dict(
        db.query(AMC.id, func.count(func.distinct(Scheme.id)))
        .join(FundFamily, FundFamily.amc_id == AMC.id)
        .join(Scheme, Scheme.fund_family_id == FundFamily.id)
        .join(PortfolioSnapshot, PortfolioSnapshot.scheme_id == Scheme.id)
        .group_by(AMC.id)
        .all()
    )

    return [
        AmcSummaryRow(
            id=amc.id,
            name=amc.name,
            fund_family_count=fund_family_counts.get(amc.id, 0),
            scheme_count=scheme_counts.get(amc.id, 0),
            schemes_with_holdings_count=holdings_counts.get(amc.id, 0),
        )
        for amc in amcs
    ]


def get_amc(db: Session, amc_id: int) -> AMC | None:
    return db.get(AMC, amc_id)


def list_schemes_for_amc(db: Session, amc_id: int) -> list[AmcSchemeRow]:
    schemes = (
        db.query(Scheme)
        .join(FundFamily, Scheme.fund_family_id == FundFamily.id)
        .filter(FundFamily.amc_id == amc_id)
        .options(joinedload(Scheme.fund_family), joinedload(Scheme.benchmark))
        .order_by(Scheme.name)
        .all()
    )
    if not schemes:
        return []

    scheme_ids = [s.id for s in schemes]
    latest_dates = dict(
        db.query(PortfolioSnapshot.scheme_id, func.max(PortfolioSnapshot.as_of_date))
        .filter(PortfolioSnapshot.scheme_id.in_(scheme_ids))
        .group_by(PortfolioSnapshot.scheme_id)
        .all()
    )

    return [
        AmcSchemeRow(
            id=s.id,
            scheme_name=s.name,
            category=s.category,
            fund_family_name=s.fund_family.name,
            benchmark_name=s.benchmark.name if s.benchmark else None,
            holdings_as_of_date=latest_dates.get(s.id),
        )
        for s in schemes
    ]
