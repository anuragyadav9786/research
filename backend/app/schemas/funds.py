"""Response schemas for fund research endpoints.

These are the only shapes the API ever returns for fund data — SQLAlchemy
models never cross the API boundary directly (Section 20).
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

DISCLAIMER = (
    "Historical performance does not guarantee future results. All figures "
    "are computed from historical NAV/benchmark data using the documented "
    "methodology in docs/analytics-methodology.md and depend on data "
    "quality and availability."
)


class VariantSummary(BaseModel):
    id: int
    plan: str
    option: str
    amfi_code: str | None
    isin: str | None
    latest_nav: float | None
    latest_nav_date: date | None


class FundSummary(BaseModel):
    id: int
    scheme_name: str
    category: str
    amc_name: str
    fund_family_name: str
    benchmark_name: str | None


class FundDetail(FundSummary):
    variants: list[VariantSummary]


class FundListResponse(BaseModel):
    items: list[FundSummary]
    has_more: bool = Field(..., description="True if more funds exist past this page's offset+limit")


class ReturnWindow(BaseModel):
    available: bool
    cagr_pct: float | None
    start_date: date | None
    end_date: date | None
    reason: str | None
    earliest_nav_date: date | None = Field(
        None,
        description=(
            "Only set when reason='scheme_too_young': the earliest NAV date "
            "in this variant's NAV history, once a complete mfapi.in backfill "
            "confirms there's nothing earlier to find. This is a real, "
            "ingested data point, not a verified legal launch/inception "
            "date — a scheme's own NFO period can predate its first NAV by a "
            "few days — so callers should present it as 'no NAV history "
            "before X', never as 'scheme launched on X'."
        ),
    )


class ReturnsResponse(BaseModel):
    as_of_date: date | None
    windows: dict[str, ReturnWindow]
    disclaimer: str = DISCLAIMER


class RiskResponse(BaseModel):
    available: bool
    reason: str | None
    observations_used: int
    risk_free_rate_pct: float = Field(..., description="Annual risk-free rate assumption used for Sharpe/Sortino")
    volatility_pct: float | None
    downside_deviation_pct: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    upside_capture_pct: float | None
    downside_capture_pct: float | None
    beta: float | None
    jensen_alpha_pct: float | None
    disclaimer: str = DISCLAIMER


class RollingReturnDistribution(BaseModel):
    count: int
    min: float | None
    p10: float | None
    p25: float | None
    median: float | None
    p75: float | None
    p90: float | None
    max: float | None


class BenchmarkConsistency(BaseModel):
    aligned_windows: int
    beat_rate_pct: float | None
    avg_excess_return: float | None
    median_excess_return: float | None
    worst_relative_return: float | None


class RollingReturnsResponse(BaseModel):
    window_years: float
    available: bool
    reason: str | None
    distribution: RollingReturnDistribution
    benchmark_consistency: BenchmarkConsistency | None
    disclaimer: str = DISCLAIMER


class RollingReturnPoint(BaseModel):
    start_date: date = Field(..., description="The day this rolling window's holding period began")
    end_date: date = Field(..., description="The day this rolling window's holding period ended")
    return_pct: float = Field(
        ..., description="Return over [start_date, end_date] — annualized for 1y windows, simple/non-annualized below"
    )


class RollingReturnSeriesResponse(BaseModel):
    """A plottable rolling-return time series (bar chart), distinct from
    RollingReturnsResponse's distribution summary — see
    fund_analytics_service.compute_rolling_return_series."""

    window: str = Field(..., description="Rolling window length: 1m, 3m, 6m, or 1y")
    lookback: str = Field(..., description="How far back the series is trimmed: 1y, 3y, 5y, or 10y")
    window_years: float
    annualized: bool = Field(..., description="True for the 1y window (CAGR); sub-annual windows are simple returns")
    available: bool
    reason: str | None
    points: list[RollingReturnPoint]
    disclaimer: str = DISCLAIMER


class InvestmentValueWindow(BaseModel):
    """One RETURN_WINDOWS_YEARS window's rupee-terms result — the amount
    a lumpsum and/or SIP invested over this exact window (same start/end
    dates compute_returns' matching window uses) would be worth today."""

    available: bool
    # "no_investment_specified" (neither lumpsum nor SIP given — never
    # returned by the API itself, which requires at least one; kept here
    # for a caller that reuses this service function directly),
    # "no_nav_history", "scheme_too_young", or "insufficient_history" —
    # same meanings as ReturnWindow.reason.
    reason: str | None
    start_date: date | None
    end_date: date | None
    earliest_nav_date: date | None
    lumpsum_invested: float | None = Field(None, description="The lumpsum amount, echoed back, if one was given")
    lumpsum_value: float | None = Field(None, description="That lumpsum's value today")
    sip_invested: float | None = Field(None, description="Total SIP contributions actually made in this window")
    sip_value: float | None = Field(None, description="Those SIP contributions' combined value today")
    sip_installments: int | None = Field(None, description="Number of SIP installments actually made in this window")
    total_value: float | None = Field(None, description="lumpsum_value + sip_value")


class InvestmentValueResponse(BaseModel):
    """Amount-terms counterpart to ReturnsResponse — "what would this
    investment be worth today" rather than "what annualized rate did this
    fund return." See fund_analytics_service.compute_investment_value."""

    as_of_date: date | None
    windows: dict[str, InvestmentValueWindow]
    disclaimer: str = DISCLAIMER


class DrawdownResponse(BaseModel):
    available: bool
    reason: str | None
    max_drawdown_pct: float | None
    peak_date: date | None
    peak_nav: float | None
    trough_date: date | None
    trough_nav: float | None
    recovered: bool | None
    recovery_date: date | None
    recovery_duration_days: int | None
    disclaimer: str = DISCLAIMER


class CategoryBenchmarkResponse(BaseModel):
    """Fund -> Category -> Benchmark context for one fund (product-upgrade
    brief Section 5) — e.g. "this fund's -31.2% max drawdown vs. its
    category's -28.4% average vs. its own benchmark index's -30.1%."
    Category figures are computed live across every same-category fund
    with enough NAV history (see category_analytics_service.py for why
    this can't be precomputed/cached server-side yet); benchmark figures
    come from the fund's own linked index series (benchmark_history) via
    the same drawdown/returns/risk analytics used everywhere else — not a
    stand-in index fund, the fund's actual named benchmark. Never a
    ranking or score: the same figure, three ways, for a neutral fund-vs-
    context reading."""

    available: bool
    reason: str | None
    category: str
    funds_included: int
    avg_cagr_3y_pct: float | None
    avg_max_drawdown_pct: float | None
    avg_volatility_pct: float | None
    benchmark_name: str | None
    benchmark_cagr_3y_pct: float | None
    benchmark_max_drawdown_pct: float | None
    benchmark_volatility_pct: float | None
    # Why the benchmark figures above are null, distinct from `reason`
    # (which explains the category average): "no_benchmark_mapped" (this
    # scheme has no known benchmark), "data_unavailable" (a benchmark is
    # identified but its price history couldn't be fetched), or
    # "insufficient_history" (price history exists but not enough of it
    # for this window). None when the benchmark figures are populated.
    benchmark_reason: str | None = None
    disclaimer: str = DISCLAIMER


class DiscoveryFilterSummary(BaseModel):
    """One named research filter's catalog entry — key, display label, and
    its exact stated definition. `criterion` is shown to the reader
    verbatim, never hidden, per Section 8's "let users investigate why a
    fund appears here" and "research filters, not rankings" rules."""

    key: str
    label: str
    criterion: str


class DiscoveryFiltersResponse(BaseModel):
    filters: list[DiscoveryFilterSummary]


class DiscoveryFundEntry(BaseModel):
    id: int
    scheme_name: str
    category: str
    amc_name: str
    # The actual value that qualified this fund for the filter — e.g. its
    # real max-drawdown percentage, not just a pass/fail flag — so a
    # reader can see exactly why it's here (Section 8's "investigate why").
    metric_label: str
    metric_value: float


class DiscoverFundsResponse(BaseModel):
    """Funds matching one named research filter (Section 8) — never a
    ranking or "Top N" list. `funds_scanned` is the real number of funds
    checked against this filter (see discovery_service.py's SCAN_CAP), not
    the size of the whole fund universe — an honest count of what this
    result actually covers, not an implied census."""

    filter: str
    label: str
    criterion: str
    funds_scanned: int
    items: list[DiscoveryFundEntry]
    disclaimer: str = DISCLAIMER


class NavPoint(BaseModel):
    date: date
    value: float


class NavHistoryResponse(BaseModel):
    """Raw NAV/benchmark series for charting (Section 22's "Performance:
    interactive charts" / "Drawdown: drawdown chart"). Deliberately just a
    data feed — no analytics computed here; that's the other endpoints."""

    variant: VariantSummary
    benchmark_name: str | None
    fund_points: list[NavPoint]
    benchmark_points: list[NavPoint]
    disclaimer: str = DISCLAIMER


class IntelligenceResponse(BaseModel):
    """A precomputed-analytics bundle for one fund. Deliberately does NOT
    yet include the qualitative "Strong/Moderate/Weak" assessment framework
    from the product spec's Section 15 — that requires the Portfolio DNA,
    Concentration, and Manager Skill engines (later phases) to ground it in
    real data. Producing a plausible-sounding label without those inputs
    would violate Rule 2/4 (no fabricated conclusions). This endpoint
    reports only what is directly computable today."""

    fund: FundDetail
    variant: VariantSummary
    returns: ReturnsResponse
    risk: RiskResponse
    rolling_3y: RollingReturnsResponse
    drawdown: DrawdownResponse
    disclaimer: str = DISCLAIMER
