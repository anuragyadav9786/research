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
    date: date
    return_pct: float = Field(
        ..., description="Rolling return ending on this date — annualized for 1y windows, simple/non-annualized below"
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
