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
}

export interface CASUnmatchedScheme {
  isin: string;
  scheme_name: string;
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
