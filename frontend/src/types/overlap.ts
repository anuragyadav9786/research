// Mirrors backend/app/schemas/overlap.py

export interface FundRef {
  id: number;
  scheme_name: string;
}

export interface CommonHolding {
  security_name: string;
  weight_a: number;
  weight_b: number;
  min_weight: number;
}

export interface SectorOverlapDetail {
  sector: string;
  weight_a: number;
  weight_b: number;
  min_weight: number;
}

export interface OverlapResponse {
  available: boolean;
  reason: string | null;
  fund_a: FundRef;
  fund_b: FundRef;
  as_of_date_a: string | null;
  as_of_date_b: string | null;
  common_securities_count: number;
  only_in_a_count: number;
  only_in_b_count: number;
  weighted_overlap_pct: number | null;
  sector_overlap_pct: number | null;
  overlap_label: string | null;
  return_correlation: number | null;
  common_holdings: CommonHolding[];
  sector_detail: SectorOverlapDetail[];
  disclaimer: string;
}
