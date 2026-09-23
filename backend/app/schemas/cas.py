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


class CASPurchaseBehavior(BaseModel):
    """Portfolio Analysis §13: this scheme's own purchase/NAV behavior —
    how many purchases were made, lumpsum vs. SIP, over what span, and at
    what NAV range. Purely descriptive: reports what happened, never a
    judgment of whether it was good or bad timing. All fields are null
    when this scheme has zero purchase-type transactions (e.g. every unit
    came in via a switch-in), never a fabricated 0/₹0."""

    purchase_count: int = Field(..., description="Total Purchase + SIP transactions")
    sip_installment_count: int
    lumpsum_count: int
    first_purchase_date: date | None = None
    latest_purchase_date: date | None = None
    lowest_purchase_nav: float | None = Field(None, description="Lowest price actually paid (amount/units), across every purchase")
    highest_purchase_nav: float | None = None
    average_purchase_nav: float | None = Field(None, description="Amount-weighted average price paid across every purchase")


class CASTransactionActivity(BaseModel):
    """Portfolio Analysis §14: how often, and for how much, the investor
    actually redeemed, switched, or otherwise transacted — one row per
    transaction_type that occurred at least once across every matched
    scheme. Purely descriptive: no framing of any category as good or bad."""

    transaction_type: str = Field(
        ..., description="PURCHASE | SIP | REDEMPTION | SWP | SWITCH_IN | SWITCH_OUT | STP_IN | STP_OUT | "
        "DIVIDEND | DIVIDEND_REINVESTMENT | BONUS | REVERSAL | OTHER"
    )
    count: int
    total_amount: float = Field(..., description="Sum of absolute transaction amounts of this type")


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
    scheme_xirr_pct: float | None = Field(
        None, description="This scheme's own money-weighted annualized return — null if it couldn't be solved"
    )
    weight_pct: float | None = Field(
        None, description="This scheme's current_value as a % of total_current_value — null if unpriced"
    )
    gain: float | None = Field(
        None,
        description="realized_gain + unrealized_gain — null if this scheme still holds units we couldn't value, "
        "which would otherwise understate the true figure",
    )
    contribution_to_gain_pct: float | None = Field(
        None, description="This scheme's gain as a % of the portfolio's total_gain — null if gain or total_gain is unknown/zero"
    )
    purchase_behavior: CASPurchaseBehavior


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


class CASHoldingPeriodBucket(BaseModel):
    label: str = Field(..., description="e.g. '< 1 year', '1-3 years', '3-5 years', '5+ years'")
    value: float = Field(..., description="Current rupee value of still-open lots in this bucket")
    weight_pct: float


class CASHoldingPeriodSummary(BaseModel):
    """Portfolio Analysis §12: how long money has actually been held —
    computed from FIFO lot accounting (analytics/cost_basis.py), never
    from a scheme's overall start date, since different lots within the
    same scheme can have very different ages. Only covers lots/
    consumptions from matched, priced schemes; fields are null/empty
    rather than a fabricated 0 when there's nothing of that kind to
    summarize (e.g. nothing has ever been sold)."""

    open_weighted_avg_days: int | None = Field(
        None, description="Value-weighted average age, in days, of currently-held (unsold) lots"
    )
    open_value_by_bucket: list[CASHoldingPeriodBucket]
    realized_avg_days: int | None = Field(None, description="Average holding period of every sold/switched-out lot")
    realized_median_days: int | None = None
    realized_consumption_count: int = Field(..., description="Number of FIFO lot consumptions realized_avg/median are over")


class CASTimeWeightedReturn(BaseModel):
    """Portfolio Analysis §6: Time-Weighted Return, annualized volatility,
    and max drawdown of the portfolio's own actual value over time —
    reconstructed from real per-scheme unit holdings and NAV history, not
    a hypothetical fixed-weight blend (see analytics/portfolio_valuation.py).
    Unlike portfolio_xirr_pct above (money-weighted — sensitive to this
    investor's own contribution timing), TWR strips out cash-flow timing
    so it measures how choppy the ride itself was. Only covers schemes
    this platform has ever priced (`priced_scheme_count` of
    matched_scheme_count) — every field is null when none are priced,
    never a fabricated 0%."""

    cumulative_twr_pct: float | None = Field(None, description="Total time-weighted return over the whole reconstructed span")
    annualized_twr_pct: float | None = None
    volatility_pct: float | None = Field(None, description="Annualized standard deviation of the TWR sub-period returns")
    max_drawdown_pct: float | None = Field(None, description="Worst peak-to-trough decline in the reconstructed value")
    drawdown_peak_date: date | None = None
    drawdown_trough_date: date | None = None
    drawdown_recovery_date: date | None = Field(
        None, description="Null if not yet recovered as of the last reconstructed date, or no drawdown to recover from"
    )
    drawdown_recovered: bool | None = None
    priced_scheme_count: int = Field(..., description="How many matched schemes this reconstruction actually covers")
    start_date: date | None = Field(None, description="First date in the reconstructed value series")
    end_date: date | None = None


class CASOverviewResponse(BaseModel):
    """Portfolio Analysis §4/§5/§7/§8/§12/§15: invested capital vs.
    current value, realized vs. unrealized gain, money-weighted (XIRR)
    return, portfolio structure (concentration + allocation), per-scheme
    contribution to overall gain, and holding-period analysis — computed
    from the CAS's full transaction ledger, not just its stated closing
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
    holding_period: CASHoldingPeriodSummary
    time_weighted_return: CASTimeWeightedReturn
    transaction_activity: list[CASTransactionActivity] = Field(
        ..., description="Breakdown of transaction count and total amount by type, across every matched scheme"
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
