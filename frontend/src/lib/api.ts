import type {
  DrawdownResponse,
  FundDetail,
  FundListResponse,
  FundSummary,
  IntelligenceResponse,
  NavHistoryResponse,
  Option,
  Plan,
  ReturnsResponse,
  RiskResponse,
  RollingReturnSeriesResponse,
  RollingReturnsResponse,
  RollingSeriesLookback,
  RollingSeriesWindow,
} from "@/types/fund";
import type { MarketRegimeBehaviorResponse, MarketRegimeSummary } from "@/types/marketRegime";
import type { OverlapResponse } from "@/types/overlap";
import type { PortfolioResponse } from "@/types/portfolio";
import type { PortfolioAnalysisResponse, PortfolioHoldingInput } from "@/types/portfolioAnalysis";
import type { StressTestResponse } from "@/types/stressTest";
import type { AISummaryResponse } from "@/types/aiSummary";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function extractErrorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI/Pydantic validation error shape: [{loc, msg, type}, ...]
    return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String(d.msg) : String(d))).join("; ");
  }
  return fallback;
}

// Every value this API serves changes at most once a day (NAV updates
// once per business day; nothing here is real-time). A short revalidation
// window lets Next.js's fetch cache answer repeat requests for the same
// URL without a fresh round trip to Render/Supabase each time, instead of
// the previous `cache: "no-store"` forcing every single page view (from
// every visitor) to hit the backend and database from scratch. This is
// purely a read-side optimization: it never delays a first-time fetch
// (including the Phase 15 lazy NAV backfill), it only avoids repeating an
// identical one within the window.
const REVALIDATE_SECONDS = 60;

async function apiGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  const response = await fetch(url.toString(), { next: { revalidate: REVALIDATE_SECONDS } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, extractErrorMessage(body, `Request to ${path} failed`));
  }
  return response.json();
}

async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, extractErrorMessage(body, `Request to ${path} failed`));
  }
  return response.json();
}

export interface FundListFilters {
  search?: string;
  category?: string;
  amc?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | undefined;
}

export function listFunds(filters: FundListFilters = {}): Promise<FundListResponse> {
  return apiGet<FundListResponse>("/api/funds", filters);
}

export function countFunds(filters: Omit<FundListFilters, "limit" | "offset"> = {}): Promise<{ count: number }> {
  return apiGet<{ count: number }>("/api/funds/count", filters);
}

// A handful of pages need every fund for a plan/option-style <select> —
// not a paged browsing list. 2000 matches the backend's own ceiling
// (see funds.py's list_funds), comfortably above the current fund count.
const ALL_FUNDS_LIMIT = 2000;

export function listAllFunds(filters: Omit<FundListFilters, "limit" | "offset"> = {}): Promise<FundSummary[]> {
  return listFunds({ ...filters, limit: ALL_FUNDS_LIMIT }).then((r) => r.items);
}

export function getFund(fundId: number): Promise<FundDetail> {
  return apiGet<FundDetail>(`/api/funds/${fundId}`);
}

export interface VariantParams {
  plan?: Plan;
  option?: Option;
  [key: string]: string | number | undefined;
}

export function getFundReturns(fundId: number, params: VariantParams = {}): Promise<ReturnsResponse> {
  return apiGet<ReturnsResponse>(`/api/funds/${fundId}/returns`, params);
}

export function getFundRisk(fundId: number, params: VariantParams = {}): Promise<RiskResponse> {
  return apiGet<RiskResponse>(`/api/funds/${fundId}/risk`, params);
}

export function getFundRollingReturns(
  fundId: number,
  params: VariantParams & { window_years?: number } = {},
): Promise<RollingReturnsResponse> {
  return apiGet<RollingReturnsResponse>(`/api/funds/${fundId}/rolling-returns`, params);
}

export function getFundRollingReturnSeries(
  fundId: number,
  params: VariantParams & { window?: RollingSeriesWindow; lookback?: RollingSeriesLookback } = {},
): Promise<RollingReturnSeriesResponse> {
  return apiGet<RollingReturnSeriesResponse>(`/api/funds/${fundId}/rolling-returns-series`, params);
}

export function getFundDrawdown(fundId: number, params: VariantParams = {}): Promise<DrawdownResponse> {
  return apiGet<DrawdownResponse>(`/api/funds/${fundId}/drawdown`, params);
}

export function getFundPortfolio(fundId: number): Promise<PortfolioResponse> {
  return apiGet<PortfolioResponse>(`/api/funds/${fundId}/portfolio`);
}

export function getFundOverlap(fundId: number, compareTo: number): Promise<OverlapResponse> {
  return apiGet<OverlapResponse>(`/api/funds/${fundId}/overlap`, { compare_to: compareTo });
}

export function getFundNavHistory(fundId: number, params: VariantParams = {}): Promise<NavHistoryResponse> {
  return apiGet<NavHistoryResponse>(`/api/funds/${fundId}/nav-history`, params);
}

export function analysePortfolio(holdings: PortfolioHoldingInput[]): Promise<PortfolioAnalysisResponse> {
  return apiPost<PortfolioAnalysisResponse>("/api/portfolio/analyse", { holdings });
}

export function getFundMarketRegimes(
  fundId: number,
  params: VariantParams = {},
): Promise<MarketRegimeBehaviorResponse> {
  return apiGet<MarketRegimeBehaviorResponse>(`/api/funds/${fundId}/market-regimes`, params);
}

export function listMarketRegimes(): Promise<MarketRegimeSummary[]> {
  return apiGet<MarketRegimeSummary[]>("/api/market/regimes");
}

export function getFundStressTest(fundId: number, params: VariantParams = {}): Promise<StressTestResponse> {
  return apiGet<StressTestResponse>(`/api/funds/${fundId}/stress-test`, params);
}

// Bundles returns + risk + rolling(3y) + drawdown into one backend call
// instead of four — the fund detail page uses this for everything except
// a non-default rolling window, which still needs its own request.
export function getFundIntelligence(fundId: number, params: VariantParams = {}): Promise<IntelligenceResponse> {
  return apiGet<IntelligenceResponse>(`/api/funds/${fundId}/intelligence`, params);
}

export function getFundAiSummary(fundId: number, params: VariantParams = {}): Promise<AISummaryResponse> {
  return apiGet<AISummaryResponse>(`/api/funds/${fundId}/ai-summary`, params);
}
