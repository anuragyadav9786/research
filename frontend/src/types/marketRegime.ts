// Mirrors backend/app/schemas/market_regime.py

export interface MarketRegimeSummary {
  id: number;
  name: string;
  regime_type: string;
  start_date: string;
  end_date: string | null;
}

export interface RegimeBehavior {
  regime_name: string;
  regime_type: string;
  start_date: string;
  end_date: string | null;
  fund_available: boolean;
  fund_return_pct: number | null;
  fund_volatility_pct: number | null;
  fund_max_drawdown_pct: number | null;
  benchmark_available: boolean;
  benchmark_return_pct: number | null;
  excess_return_pct: number | null;
  outperformed: boolean | null;
  summary: string;
}

export interface MarketRegimeBehaviorResponse {
  regimes: RegimeBehavior[];
  regimes_with_comparison: number;
  regimes_outperformed: number;
  methodology_note: string;
  disclaimer: string;
}
