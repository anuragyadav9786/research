import type {
  DrawdownResponse,
  FundDetail,
  FundSummary,
  NavHistoryResponse,
  Option,
  Plan,
  ReturnsResponse,
  RiskResponse,
  RollingReturnsResponse,
} from "@/types/fund";
import type { OverlapResponse } from "@/types/overlap";
import type { PortfolioResponse } from "@/types/portfolio";
import type { PortfolioAnalysisResponse, PortfolioHoldingInput } from "@/types/portfolioAnalysis";

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

async function apiGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  const response = await fetch(url.toString(), { cache: "no-store" });
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
  [key: string]: string | number | undefined;
}

export function listFunds(filters: FundListFilters = {}): Promise<FundSummary[]> {
  return apiGet<FundSummary[]>("/api/funds", filters);
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
