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

export interface CASParseResponse {
  as_of_date: string | null;
  matched_holdings: CASMatchedHolding[];
  unmatched_holdings: CASUnmatchedHolding[];
  total_market_value: number;
  matched_market_value: number;
  disclaimer: string;
}
