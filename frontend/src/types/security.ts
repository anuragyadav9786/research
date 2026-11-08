// Mirrors backend/app/schemas/security.py

export interface SecuritySummary {
  id: number;
  name: string;
  isin: string | null;
  instrument_type: string | null;
  sector: string | null;
}

export interface SecuritySearchResponse {
  items: SecuritySummary[];
}

export interface HolderRow {
  scheme_id: number;
  scheme_name: string;
  amc_name: string;
  as_of_date: string;
  weight_pct: number;
  market_value: number | null;
}

export interface SecurityHoldersResponse {
  security: SecuritySummary;
  holders: HolderRow[];
  total_holders: number;
}
