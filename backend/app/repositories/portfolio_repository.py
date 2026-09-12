"""Read-only data access for a scheme's disclosed portfolio holdings.

Holdings hang off `scheme_id`, not `scheme_variant_id` — the underlying
portfolio is identical across a scheme's direct/regular, growth/IDCW
variants (see docs/BUILD_PLAN.md's identifier-hierarchy note), so this is
deliberately variant-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.reference import Sector, Security
from app.models.timeseries import DataSource, PortfolioHolding, PortfolioSnapshot


@dataclass
class HoldingRow:
    security_name: str
    sector_name: str | None
    market_cap_category: str | None
    weight_pct: float


def get_latest_snapshot(db: Session, scheme_id: int) -> PortfolioSnapshot | None:
    return (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.scheme_id == scheme_id)
        .order_by(PortfolioSnapshot.as_of_date.desc())
        .first()
    )


def get_snapshot_source(db: Session, snapshot: PortfolioSnapshot) -> DataSource | None:
    return db.get(DataSource, snapshot.source_id)


def get_holdings(db: Session, snapshot_id: int) -> list[HoldingRow]:
    # PortfolioHolding has no ORM relationship to Security defined — join
    # explicitly rather than adding one just for this single read.
    rows = (
        db.query(PortfolioHolding, Security)
        .join(Security, PortfolioHolding.security_id == Security.id)
        .filter(PortfolioHolding.snapshot_id == snapshot_id)
        .order_by(PortfolioHolding.weight_pct.desc())
        .all()
    )

    sector_ids = {security.sector_id for _, security in rows if security.sector_id is not None}
    sectors_by_id = {}
    if sector_ids:
        sectors_by_id = {s.id: s.name for s in db.query(Sector).filter(Sector.id.in_(sector_ids)).all()}

    return [
        HoldingRow(
            security_name=security.name,
            sector_name=sectors_by_id.get(security.sector_id),
            market_cap_category=security.market_cap_category,
            weight_pct=float(holding.weight_pct),
        )
        for holding, security in rows
    ]
