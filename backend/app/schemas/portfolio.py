"""Response schemas for the Phase 7 Holdings Engine — Portfolio DNA
(market-cap/sector composition) and single-fund concentration metrics.

Cross-fund "hidden concentration" (Section 9's other half) needs the
Overlap Engine (Phase 8) and isn't in scope here.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.funds import DISCLAIMER


class HoldingItem(BaseModel):
    rank: int
    security_name: str
    sector: str | None
    market_cap_category: str | None
    weight_pct: float


class AllocationSlice(BaseModel):
    label: str
    weight_pct: float


class PortfolioResponse(BaseModel):
    available: bool
    reason: str | None
    as_of_date: date | None
    source_name: str | None
    total_holdings: int
    total_disclosed_weight_pct: float | None
    top_holdings: list[HoldingItem]
    top5_weight_pct: float | None
    top10_weight_pct: float | None
    hhi: float | None
    hhi_label: str | None
    sector_allocation: list[AllocationSlice]
    market_cap_allocation: list[AllocationSlice]
    disclaimer: str = DISCLAIMER
