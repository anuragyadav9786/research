"""Response schemas for Phase 10's Market-Cycle Behaviour Engine."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.funds import DISCLAIMER

METHODOLOGY_NOTE = (
    "Market regimes in the current sample dataset are illustrative date windows "
    "derived from the Phase 2 synthetic seed data's own shape, not verified "
    "real-world market classifications. See docs/data-sources.md."
)


class MarketRegimeSummary(BaseModel):
    id: int
    name: str
    regime_type: str
    start_date: date
    end_date: date | None


class RegimeBehavior(BaseModel):
    regime_name: str
    regime_type: str
    start_date: date
    end_date: date | None
    fund_available: bool
    fund_return_pct: float | None
    fund_volatility_pct: float | None
    fund_max_drawdown_pct: float | None
    benchmark_available: bool
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    outperformed: bool | None
    summary: str


class MarketRegimeBehaviorResponse(BaseModel):
    regimes: list[RegimeBehavior]
    regimes_with_comparison: int
    regimes_outperformed: int
    methodology_note: str = METHODOLOGY_NOTE
    disclaimer: str = DISCLAIMER
