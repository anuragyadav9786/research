// Mirrors backend/app/schemas/portfolio_analysis.py

import type { AllocationSlice } from "@/types/portfolio";

export type { AllocationSlice };

export interface PortfolioHoldingInput {
  fund_id: number;
  weight_pct: number;
}

export interface FundWeight {
  fund_id: number;
  scheme_name: string;
  weight_pct: number;
}

export interface CombinedHolding {
  rank: number;
  security_name: string;
  effective_weight_pct: number;
}

export interface ConcentrationSummary {
  hhi: number;
  hhi_label: string;
  top5_weight_pct: number;
  top10_weight_pct: number;
}

export interface PairwiseOverlapItem {
  fund_a_id: number;
  fund_a_name: string;
  fund_b_id: number;
  fund_b_name: string;
  weighted_overlap_pct: number;
  overlap_label: string;
}

export interface PortfolioRisk {
  available: boolean;
  reason: string | null;
  volatility_pct: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  observations_used: number;
}

export interface PortfolioDrawdown {
  available: boolean;
  reason: string | null;
  max_drawdown_pct: number | null;
  peak_date: string | null;
  trough_date: string | null;
  recovered: boolean | null;
  recovery_date: string | null;
  recovery_duration_days: number | null;
}

export interface PortfolioAnalysisResponse {
  funds: FundWeight[];
  total_weight_pct: number;
  combined_top_holdings: CombinedHolding[];
  sector_allocation: AllocationSlice[];
  market_cap_allocation: AllocationSlice[];
  concentration: ConcentrationSummary | null;
  pairwise_overlap: PairwiseOverlapItem[];
  average_pairwise_correlation: number | null;
  risk: PortfolioRisk;
  drawdown: PortfolioDrawdown;
  disclaimer: string;
}
