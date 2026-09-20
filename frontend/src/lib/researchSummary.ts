import { formatDate, formatNumber, formatPct } from "@/lib/format";
import { cagrContextSentence, drawdownContextSentence } from "@/lib/metricInterpretation";
import type {
  CategoryBenchmarkResponse,
  DrawdownResponse,
  ReturnsResponse,
  RollingReturnsResponse,
} from "@/types/fund";
import type { MarketRegimeBehaviorResponse } from "@/types/marketRegime";
import type { PortfolioResponse } from "@/types/portfolio";

export interface ResearchSummaryPoint {
  heading: string;
  sentence: string;
}

const RETURN_WINDOW_ORDER = ["10y", "7y", "5y", "3y", "1y"] as const;
const RETURN_WINDOW_LABELS: Record<string, string> = {
  "1y": "1-year",
  "3y": "3-year",
  "5y": "5-year",
  "7y": "7-year",
  "10y": "10-year",
};

/** A template-generated, always-visible research summary — no LLM call,
 * so it never depends on ANTHROPIC_API_KEY being configured and can never
 * fabricate a number, unlike a free-text model response (see
 * AiSummaryPanel/ai_explanation_service.py for the AI-generated,
 * opt-in alternative this sits alongside, not replaces). Every sentence
 * here is built directly from a single already-computed API field —
 * no interpretation beyond stating what the data shows, per the brief's
 * "The historical data indicates..." register, and a metric with
 * insufficient history says so rather than being silently omitted. */
export function buildResearchSummary(input: {
  category: string;
  returns: ReturnsResponse;
  drawdown: DrawdownResponse;
  rolling: RollingReturnsResponse;
  marketRegimes: MarketRegimeBehaviorResponse;
  portfolio: PortfolioResponse;
  categoryBenchmark: CategoryBenchmarkResponse | null;
}): ResearchSummaryPoint[] {
  const { category, returns, drawdown, rolling, marketRegimes, portfolio, categoryBenchmark } = input;
  const points: ResearchSummaryPoint[] = [];

  const longestWindow = RETURN_WINDOW_ORDER.map((key) => ({ key, window: returns.windows[key] })).find(
    ({ window }) => window?.available,
  );
  points.push({
    heading: "Long-Term Return Behaviour",
    sentence: longestWindow
      ? `Over the longest period with enough NAV history (${RETURN_WINDOW_LABELS[longestWindow.key]}), the fund's annualised return has been ${formatPct(longestWindow.window.cagr_pct)}. This is a point-to-point figure — it depends on the exact start and end dates measured.`
      : "The historical data available so far isn't enough to report a long-term annualised return.",
  });

  const { min, median, max } = rolling.distribution;
  points.push({
    heading: "Consistency of Outcomes",
    sentence:
      rolling.available && min !== null && max !== null && median !== null
        ? `During the analysed period, rolling ${rolling.window_years}-year returns ranged from ${formatPct(min)} to ${formatPct(max)}, with a typical (median) outcome of ${formatPct(median)}.${
            rolling.benchmark_consistency?.beat_rate_pct != null
              ? ` The fund beat its benchmark in ${formatNumber(rolling.benchmark_consistency.beat_rate_pct, 0)}% of these rolling windows.`
              : ""
          }`
        : "Not enough NAV history yet to report how consistent the fund's outcomes have been across rolling periods.",
  });

  points.push({
    heading: "Historical Drawdown Behaviour",
    sentence:
      drawdown.available && drawdown.max_drawdown_pct !== null
        ? `The fund's largest historical decline from a peak was ${formatPct(drawdown.max_drawdown_pct, 1)}, reached between ${formatDate(drawdown.peak_date)} and ${formatDate(drawdown.trough_date)}.`
        : "Not enough NAV history yet to report a historical drawdown.",
  });

  points.push({
    heading: "Recovery Characteristics",
    sentence:
      drawdown.available && drawdown.recovered === true && drawdown.recovery_duration_days != null
        ? `Following that decline, the fund recovered to its prior peak by ${formatDate(drawdown.recovery_date)} — ${drawdown.recovery_duration_days} days after the trough.`
        : drawdown.available && drawdown.recovered === false
          ? "As of the latest available data, the fund has not yet recovered to its pre-drawdown peak."
          : "Not enough NAV history yet to report recovery characteristics.",
  });

  const relativeClauses: string[] = [];
  if (categoryBenchmark && longestWindow?.window.cagr_pct != null && longestWindow.key === "3y") {
    const clause = cagrContextSentence(
      longestWindow.window.cagr_pct,
      categoryBenchmark.avg_cagr_3y_pct,
      category,
      categoryBenchmark.benchmark_cagr_3y_pct,
      categoryBenchmark.benchmark_name,
    );
    if (clause) relativeClauses.push(clause);
  }
  if (categoryBenchmark && drawdown.available && drawdown.max_drawdown_pct !== null) {
    const clause = drawdownContextSentence(
      drawdown.max_drawdown_pct,
      categoryBenchmark.avg_max_drawdown_pct,
      category,
      categoryBenchmark.benchmark_max_drawdown_pct,
      categoryBenchmark.benchmark_name,
    );
    if (clause) relativeClauses.push(clause);
  }
  if (marketRegimes.regimes_with_comparison > 0) {
    relativeClauses.push(
      `Across ${marketRegimes.regimes_with_comparison} historical market-cycle periods examined, the fund outperformed its benchmark in ${marketRegimes.regimes_outperformed} of them.`,
    );
  }
  points.push({
    heading: "Relative to Benchmark & Category",
    sentence:
      relativeClauses.length > 0
        ? relativeClauses.join(" ")
        : "Not enough comparable data yet to place this fund against its category or benchmark.",
  });

  points.push({
    heading: "Portfolio Observations",
    sentence:
      portfolio.available && portfolio.top5_weight_pct !== null
        ? `Disclosed holdings as of ${formatDate(portfolio.as_of_date)} show ${
            portfolio.hhi_label === "high_concentration"
              ? "high"
              : portfolio.hhi_label === "moderate_concentration"
                ? "moderate"
                : "diversified"
          } concentration, with the top 5 holdings accounting for ${formatNumber(portfolio.top5_weight_pct, 1)}% of the portfolio across ${portfolio.total_holdings} disclosed holdings.`
        : "No disclosed portfolio holdings data is available for this fund yet.",
  });

  return points;
}
