"""Response shape for CAS (Consolidated Account Statement) upload/parse —
see data_pipeline/normalization/cas_parser.py and app/services/cas_service.py.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

CAS_DISCLAIMER = (
    "Holdings and values are read directly from your uploaded statement as of the date it "
    "was generated — they are not refreshed live and may not reflect transactions since then. "
    "A scheme not yet in our fund database is excluded from analysis, never guessed at."
)


class CASMatchedHolding(BaseModel):
    fund_id: int
    scheme_name: str = Field(..., description="This platform's own name for the matched scheme")
    isin: str
    market_value: float = Field(..., description="Market value as stated in the CAS, as of its generation date")
    weight_pct: float = Field(..., description="market_value as a % of the total across every matched holding")


class CASUnmatchedHolding(BaseModel):
    scheme_name: str = Field(..., description="The scheme name as it appears in the CAS itself")
    isin: str
    market_value: float
    reason: str = Field(..., description="Why this holding couldn't be included, e.g. 'isin_not_found'")


class CASSchemeOverview(BaseModel):
    """One matched scheme's contribution to the portfolio-level overview
    — invested capital, cost basis, and current value, all from replaying
    this scheme's own transaction history via FIFO lot accounting (see
    analytics/cost_basis.py)."""

    fund_id: int
    scheme_name: str
    isin: str
    invested_amount: float = Field(..., description="Real external money paid in (Purchase + SIP only, never switch-in)")
    realized_gain: float = Field(..., description="Gain/loss already locked in by past redemptions/switch-outs")
    remaining_units: float
    weighted_average_purchase_nav: float | None = Field(None, description="Null if nothing is currently held")
    current_nav: float | None = Field(None, description="Null if this scheme has no NAV history in our database yet")
    current_nav_date: date | None
    current_value: float | None
    unrealized_gain: float | None


class CASUnmatchedScheme(BaseModel):
    isin: str
    scheme_name: str


class CASConcentrationSummary(BaseModel):
    """Herfindahl-Hirschman Index and top-N weight, at whatever level
    this summary is grouped by (scheme/AMC/category) — see
    analytics/concentration.py for the formulas and the DOJ/FTC-derived
    hhi_label thresholds."""

    top1_pct: float
    top3_pct: float
    top5_pct: float
    top10_pct: float
    hhi: float
    hhi_label: str = Field(..., description="'diversified' | 'moderate_concentration' | 'high_concentration'")
    count: int | None = Field(None, description="Number of distinct groups (AMCs/categories) — omitted for scheme-level")


class CASAllocationSlice(BaseModel):
    label: str
    value: float = Field(..., description="Current rupee value in this slice")
    weight_pct: float


class CASPortfolioStructure(BaseModel):
    """Portfolio Analysis §7/§8: how the portfolio's current rupee value
    (not invested amount) breaks down by scheme, AMC, category, and
    broad asset class — and, for equity holdings, by market-cap/style.
    Asset-class and equity-style labels come only from each scheme's own
    stated category string (data_pipeline/normalization/
    category_classification.py) — never guessed from a scheme's name or
    its disclosed underlying holdings."""

    scheme_concentration: CASConcentrationSummary
    amc_concentration: CASConcentrationSummary
    category_concentration: CASConcentrationSummary
    asset_allocation: list[CASAllocationSlice]
    equity_style_allocation: list[CASAllocationSlice] = Field(
        ..., description="Market-cap/style breakdown within equity holdings only, as a % of the whole portfolio"
    )
    amc_allocation: list[CASAllocationSlice]
    category_allocation: list[CASAllocationSlice]


class CASOverviewResponse(BaseModel):
    """Portfolio Analysis §4/§5/§7/§8: invested capital vs. current
    value, realized vs. unrealized gain, money-weighted (XIRR) return,
    and portfolio structure (concentration + allocation) — computed from
    the CAS's full transaction ledger, not just its stated closing
    balances. Covers only ISIN-matched schemes; anything unmatched is
    listed, never silently folded into the totals."""

    total_invested: float
    total_current_value: float
    total_realized_gain: float
    total_unrealized_gain: float
    total_gain: float = Field(..., description="total_realized_gain + total_unrealized_gain")
    portfolio_xirr_pct: float | None = Field(
        None, description="Money-weighted annualized return, as a percentage — null if it couldn't be solved"
    )
    matched_scheme_count: int
    per_scheme: list[CASSchemeOverview]
    unmatched_schemes: list[CASUnmatchedScheme]
    structure: CASPortfolioStructure | None = Field(
        None, description="Null if no matched holding has a usable current value yet"
    )


class CASParseResponse(BaseModel):
    as_of_date: date | None = Field(None, description="The statement's own generation/end date, if found")
    matched_holdings: list[CASMatchedHolding]
    unmatched_holdings: list[CASUnmatchedHolding]
    total_market_value: float = Field(..., description="Sum of every currently-held position found in the statement")
    matched_market_value: float = Field(..., description="Sum of only the matched holdings — what weight_pct is based on")
    overview: CASOverviewResponse | None = Field(
        None, description="Invested/current-value/XIRR overview computed from the full transaction ledger"
    )
    disclaimer: str = CAS_DISCLAIMER
