// Mirrors backend/app/schemas/funds.py — kept hand-in-sync since the
// backend doesn't currently publish a generated client. If this drifts,
// runtime response validation would need to move to a shared schema
// (e.g. generating types from the OpenAPI schema at /openapi.json) rather
// than trusting these types blindly forever.

export type Plan = "direct" | "regular";
export type Option = "growth" | "idcw";

export interface VariantSummary {
  id: number;
  plan: Plan;
  option: Option;
  amfi_code: string | null;
  isin: string | null;
  latest_nav: number | null;
  latest_nav_date: string | null;
}

export interface FundSummary {
  id: number;
  scheme_name: string;
  category: string;
  amc_name: string;
  fund_family_name: string;
  benchmark_name: string | null;
}

export interface FundDetail extends FundSummary {
  variants: VariantSummary[];
}

export interface FundListResponse {
  items: FundSummary[];
  has_more: boolean;
}

export interface ReturnWindow {
  available: boolean;
  cagr_pct: number | null;
  start_date: string | null;
  end_date: string | null;
  reason: string | null;
}

export interface ReturnsResponse {
  as_of_date: string | null;
  windows: Record<"1y" | "3y" | "5y" | "7y" | "10y", ReturnWindow>;
  disclaimer: string;
}

export interface RiskResponse {
  available: boolean;
  reason: string | null;
  observations_used: number;
  risk_free_rate_pct: number;
  volatility_pct: number | null;
  downside_deviation_pct: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  upside_capture_pct: number | null;
  downside_capture_pct: number | null;
  beta: number | null;
  jensen_alpha_pct: number | null;
  disclaimer: string;
}

export interface RollingReturnDistribution {
  count: number;
  min: number | null;
  p10: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  p90: number | null;
  max: number | null;
}

export interface BenchmarkConsistency {
  aligned_windows: number;
  beat_rate_pct: number | null;
  avg_excess_return: number | null;
  median_excess_return: number | null;
  worst_relative_return: number | null;
}

export interface RollingReturnsResponse {
  window_years: number;
  available: boolean;
  reason: string | null;
  distribution: RollingReturnDistribution;
  benchmark_consistency: BenchmarkConsistency | null;
  disclaimer: string;
}

export type RollingSeriesWindow = "1m" | "3m" | "6m" | "1y";
export type RollingSeriesLookback = "1y" | "3y" | "5y" | "10y";

export interface RollingReturnPoint {
  date: string;
  return_pct: number;
}

export interface RollingReturnSeriesResponse {
  window: RollingSeriesWindow;
  lookback: RollingSeriesLookback;
  window_years: number;
  annualized: boolean;
  available: boolean;
  reason: string | null;
  points: RollingReturnPoint[];
  disclaimer: string;
}

export interface DrawdownResponse {
  available: boolean;
  reason: string | null;
  max_drawdown_pct: number | null;
  peak_date: string | null;
  peak_nav: number | null;
  trough_date: string | null;
  trough_nav: number | null;
  recovered: boolean | null;
  recovery_date: string | null;
  recovery_duration_days: number | null;
  disclaimer: string;
}

export interface CategoryBenchmarkResponse {
  available: boolean;
  reason: string | null;
  category: string;
  funds_included: number;
  avg_cagr_3y_pct: number | null;
  avg_max_drawdown_pct: number | null;
  avg_volatility_pct: number | null;
  benchmark_name: string | null;
  benchmark_cagr_3y_pct: number | null;
  benchmark_max_drawdown_pct: number | null;
  benchmark_volatility_pct: number | null;
  disclaimer: string;
}

export interface NavPoint {
  date: string;
  value: number;
}

export interface NavHistoryResponse {
  variant: VariantSummary;
  benchmark_name: string | null;
  fund_points: NavPoint[];
  benchmark_points: NavPoint[];
  disclaimer: string;
}

export interface IntelligenceResponse {
  fund: FundDetail;
  variant: VariantSummary;
  returns: ReturnsResponse;
  risk: RiskResponse;
  rolling_3y: RollingReturnsResponse;
  drawdown: DrawdownResponse;
  disclaimer: string;
}
