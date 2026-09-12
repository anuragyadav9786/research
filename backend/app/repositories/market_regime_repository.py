"""Read-only access to the market_regimes reference table."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.reference import MarketRegime


def list_regimes(db: Session) -> list[MarketRegime]:
    return db.query(MarketRegime).order_by(MarketRegime.start_date).all()
