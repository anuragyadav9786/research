"""Request/response schemas for Phase 9's multi-fund Portfolio Analysis.

Stateless by design: the caller supplies a hypothetical set of funds and
weights on each request rather than a persisted, owned "my portfolio"
record — there is no authentication system yet (Section 25 lists it as
"expandable later," not built), and persisting portfolio data with no
account to own it would be a half-built data model. `investor_portfolios`
et al. in the schema are ready for that once auth exists.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.funds import DISCLAIMER
from app.schemas.portfolio import AllocationSlice

MIN_HOLDINGS = 2
MAX_HOLDINGS = 10


class PortfolioHoldingInput(BaseModel):
    fund_id: int
    weight_pct: float = Field(gt=0, le=100)


class PortfolioAnalyseRequest(BaseModel):
    holdings: list[PortfolioHoldingInput] = Field(min_length=MIN_HOLDINGS, max_length=MAX_HOLDINGS)


class FundWeight(BaseModel):
    fund_id: int
    scheme_name: str
    weight_pct: float


class CombinedHolding(BaseModel):
    rank: int
    security_name: str
    effective_weight_pct: float


class ConcentrationSummary(BaseModel):
    hhi: float
    hhi_label: str
    top5_weight_pct: float
    top10_weight_pct: float


class PairwiseOverlapItem(BaseModel):
    fund_a_id: int
    fund_a_name: str
    fund_b_id: int
    fund_b_name: str
    weighted_overlap_pct: float
    overlap_label: str


class PortfolioRisk(BaseModel):
    available: bool
    reason: str | None
    volatility_pct: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    observations_used: int


class PortfolioDrawdown(BaseModel):
    available: bool
    reason: str | None
    max_drawdown_pct: float | None
    peak_date: date | None
    trough_date: date | None
    recovered: bool | None
    recovery_date: date | None
    recovery_duration_days: int | None


class PortfolioAnalysisResponse(BaseModel):
    funds: list[FundWeight]
    total_weight_pct: float
    combined_top_holdings: list[CombinedHolding]
    sector_allocation: list[AllocationSlice]
    market_cap_allocation: list[AllocationSlice]
    concentration: ConcentrationSummary | None
    pairwise_overlap: list[PairwiseOverlapItem]
    average_pairwise_correlation: float | None
    risk: PortfolioRisk
    drawdown: PortfolioDrawdown
    disclaimer: str = DISCLAIMER
