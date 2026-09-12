"""Response schema for the Phase 8 pairwise Fund Overlap Engine."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.funds import DISCLAIMER


class FundRef(BaseModel):
    id: int
    scheme_name: str


class CommonHolding(BaseModel):
    security_name: str
    weight_a: float
    weight_b: float
    min_weight: float


class SectorOverlapDetail(BaseModel):
    sector: str
    weight_a: float
    weight_b: float
    min_weight: float


class OverlapResponse(BaseModel):
    available: bool
    reason: str | None
    fund_a: FundRef
    fund_b: FundRef
    as_of_date_a: date | None
    as_of_date_b: date | None
    common_securities_count: int
    only_in_a_count: int
    only_in_b_count: int
    weighted_overlap_pct: float | None
    sector_overlap_pct: float | None
    overlap_label: str | None
    return_correlation: float | None
    common_holdings: list[CommonHolding]
    sector_detail: list[SectorOverlapDetail]
    disclaimer: str = DISCLAIMER
