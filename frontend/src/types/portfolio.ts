// Mirrors backend/app/schemas/portfolio.py

export interface HoldingItem {
  rank: number;
  security_id: number;
  security_name: string;
  sector: string | null;
  market_cap_category: string | null;
  instrument_type: string | null;
  credit_rating: string | null;
  ytm_pct: number | null;
  weight_pct: number;
}

export interface AllocationSlice {
  label: string;
  weight_pct: number;
}

export interface PortfolioResponse {
  available: boolean;
  reason: string | null;
  as_of_date: string | null;
  source_name: string | null;
  total_holdings: number;
  total_disclosed_weight_pct: number | null;
  top_holdings: HoldingItem[];
  top5_weight_pct: number | null;
  top10_weight_pct: number | null;
  hhi: number | null;
  hhi_label: string | null;
  sector_allocation: AllocationSlice[];
  market_cap_allocation: AllocationSlice[];
  instrument_type_allocation: AllocationSlice[];
  credit_quality_allocation: AllocationSlice[];
  credit_quality_coverage_pct: number | null;
  average_ytm_pct: number | null;
  disclaimer: string;
}
