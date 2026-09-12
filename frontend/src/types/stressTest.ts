// Mirrors backend/app/schemas/stress_test.py

export interface ScenarioResult {
  scenario_id: string;
  name: string;
  description: string;
  shock_type: "index" | "sector" | "market_cap" | "unmodeled";
  shock_pct: number | null;
  available: boolean;
  reason: string | null;
  exposure_pct: number | null;
  estimated_impact_pct: number | null;
}

export interface StressTestResponse {
  fund_beta: number | null;
  scenarios: ScenarioResult[];
  hypothetical_notice: string;
  disclaimer: string;
}
