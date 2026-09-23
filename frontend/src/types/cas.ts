export interface CASMatchedHolding {
  fund_id: number;
  scheme_name: string;
  isin: string;
  market_value: number;
  weight_pct: number;
}

export interface CASUnmatchedHolding {
  scheme_name: string;
  isin: string;
  market_value: number;
  reason: string;
}

export interface CASSchemeOverview {
  fund_id: number;
  scheme_name: string;
  isin: string;
  invested_amount: number;
  realized_gain: number;
  remaining_units: number;
  weighted_average_purchase_nav: number | null;
  current_nav: number | null;
  current_nav_date: string | null;
  current_value: number | null;
  unrealized_gain: number | null;
  scheme_xirr_pct: number | null;
  weight_pct: number | null;
  gain: number | null;
  contribution_to_gain_pct: number | null;
}

export interface CASUnmatchedScheme {
  isin: string;
  scheme_name: string;
}

export interface CASConcentrationSummary {
  top1_pct: number;
  top3_pct: number;
  top5_pct: number;
  top10_pct: number;
  hhi: number;
  hhi_label: "diversified" | "moderate_concentration" | "high_concentration";
  count: number | null;
}

export interface CASAllocationSlice {
  label: string;
  value: number;
  weight_pct: number;
}

export interface CASPortfolioStructure {
  scheme_concentration: CASConcentrationSummary;
  amc_concentration: CASConcentrationSummary;
  category_concentration: CASConcentrationSummary;
  asset_allocation: CASAllocationSlice[];
  equity_style_allocation: CASAllocationSlice[];
  amc_allocation: CASAllocationSlice[];
  category_allocation: CASAllocationSlice[];
}

export interface CASHoldingPeriodBucket {
  label: string;
  value: number;
  weight_pct: number;
}

export interface CASHoldingPeriodSummary {
  open_weighted_avg_days: number | null;
  open_value_by_bucket: CASHoldingPeriodBucket[];
  realized_avg_days: number | null;
  realized_median_days: number | null;
  realized_consumption_count: number;
}

export interface CASTimeWeightedReturn {
  cumulative_twr_pct: number | null;
  annualized_twr_pct: number | null;
  volatility_pct: number | null;
  max_drawdown_pct: number | null;
  drawdown_peak_date: string | null;
  drawdown_trough_date: string | null;
  drawdown_recovery_date: string | null;
  drawdown_recovered: boolean | null;
  priced_scheme_count: number;
  start_date: string | null;
  end_date: string | null;
}

export interface CASOverviewResponse {
  total_invested: number;
  total_current_value: number;
  total_realized_gain: number;
  total_unrealized_gain: number;
  total_gain: number;
  portfolio_xirr_pct: number | null;
  matched_scheme_count: number;
  per_scheme: CASSchemeOverview[];
  unmatched_schemes: CASUnmatchedScheme[];
  structure: CASPortfolioStructure | null;
  holding_period: CASHoldingPeriodSummary;
  time_weighted_return: CASTimeWeightedReturn;
}

export interface CASParseResponse {
  as_of_date: string | null;
  matched_holdings: CASMatchedHolding[];
  unmatched_holdings: CASUnmatchedHolding[];
  total_market_value: number;
  matched_market_value: number;
  overview: CASOverviewResponse | null;
  disclaimer: string;
}
