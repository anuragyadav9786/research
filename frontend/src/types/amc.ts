// Mirrors backend/app/schemas/amc.py

export interface AmcSummary {
  id: number;
  name: string;
  fund_family_count: number;
  scheme_count: number;
  schemes_with_holdings_count: number;
}

export interface AmcListResponse {
  items: AmcSummary[];
}

export interface AmcSchemeRow {
  id: number;
  scheme_name: string;
  category: string;
  fund_family_name: string;
  benchmark_name: string | null;
  holdings_as_of_date: string | null;
}

export interface AmcDetailResponse {
  id: number;
  name: string;
  schemes: AmcSchemeRow[];
}
