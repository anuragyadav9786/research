import { formatNumber, formatPct } from "@/lib/format";
import type { RollingReturnDistribution } from "@/types/fund";

export interface MetricZone {
  /** Upper bound of this zone, in the metric's own units. Zones are given
   * in ascending order; the last zone's `to` must equal `scaleMax`. */
  to: number;
  label: string;
  colorClass: string;
}

export interface MetricInterpretation {
  /** Tier 1 — always-visible plain-English read of the number. */
  sentence: string;
  verdictLabel: string;
  verdictColorClass: string;
  /** Tier 2 — the shared-scale bar this value gets positioned on. */
  scaleMin: number;
  scaleMax: number;
  zones: MetricZone[];
}

// Every threshold below is a commonly-cited rule-of-thumb band for Indian/
// global mutual-fund risk metrics (Sharpe >1 "good", downside capture
// <100% "defensive", etc.) — a heuristic reading to make one number
// legible in one sentence, not a claim about this specific fund's peers or
// percentile rank (no cross-fund distribution data backs that; see
// PERSONAS in constants.ts for the same "no data we can't back" rule).

function zone(to: number, label: string, colorClass: string): MetricZone {
  return { to, label, colorClass };
}

export function interpretSharpe(value: number | null): MetricInterpretation | null {
  if (value === null) return null;
  const scaleMin = -1;
  const scaleMax = 3;
  const zones = [
    zone(0, "Poor", "bg-rose-900/60"),
    zone(1, "Fair", "bg-amber-900/60"),
    zone(2, "Good", "bg-emerald-900/60"),
    zone(scaleMax, "Excellent", "bg-emerald-600/60"),
  ];
  const [verdictLabel, verdictColorClass, read] =
    value < 0
      ? ["Poor", "text-rose-400", "lost money on a risk-adjusted basis"]
      : value < 1
        ? ["Fair", "text-amber-400", "modest return for the volatility taken on"]
        : value < 2
          ? ["Good", "text-emerald-400", "solid return for the volatility taken on"]
          : ["Excellent", "text-emerald-400", "strong return for the volatility taken on"];
  return {
    sentence: `Sharpe ratio of ${formatNumber(value)} — ${read}.`,
    verdictLabel,
    verdictColorClass,
    scaleMin,
    scaleMax,
    zones,
  };
}

export function interpretSortino(value: number | null): MetricInterpretation | null {
  if (value === null) return null;
  const scaleMin = -1;
  const scaleMax = 4;
  const zones = [
    zone(0, "Poor", "bg-rose-900/60"),
    zone(1, "Fair", "bg-amber-900/60"),
    zone(2.5, "Good", "bg-emerald-900/60"),
    zone(scaleMax, "Excellent", "bg-emerald-600/60"),
  ];
  const [verdictLabel, verdictColorClass, read] =
    value < 0
      ? ["Poor", "text-rose-400", "lost money against its own downside risk"]
      : value < 1
        ? ["Fair", "text-amber-400", "modest return against its own downside risk"]
        : value < 2.5
          ? ["Good", "text-emerald-400", "solid return against its own downside risk"]
          : ["Excellent", "text-emerald-400", "strong return against its own downside risk"];
  return {
    sentence: `Sortino ratio of ${formatNumber(value)} — ${read} (unlike Sharpe, only downside swings count against it).`,
    verdictLabel,
    verdictColorClass,
    scaleMin,
    scaleMax,
    zones,
  };
}

export function interpretVolatility(value: number | null): MetricInterpretation | null {
  if (value === null) return null;
  const scaleMin = 0;
  const scaleMax = 40;
  const zones = [
    zone(10, "Low", "bg-slate-700"),
    zone(20, "Moderate", "bg-slate-600"),
    zone(scaleMax, "High", "bg-slate-500"),
  ];
  const [verdictLabel, verdictColorClass, read] =
    value < 10
      ? ["Low", "text-slate-300", "a relatively smooth NAV path year to year"]
      : value < 20
        ? ["Moderate", "text-slate-300", "typical equity-fund swings year to year"]
        : ["High", "text-slate-300", "sharp swings year to year — not for a nervous investor"];
  return {
    sentence: `Annualized volatility of ${formatNumber(value)}% — ${read}. Volatility isn't inherently bad — it's the price of admission for higher long-run growth, not a defect.`,
    verdictLabel,
    verdictColorClass,
    scaleMin,
    scaleMax,
    zones,
  };
}

export function interpretDownsideDeviation(value: number | null): MetricInterpretation | null {
  if (value === null) return null;
  const scaleMin = 0;
  const scaleMax = 30;
  const zones = [
    zone(7, "Low", "bg-slate-700"),
    zone(15, "Moderate", "bg-slate-600"),
    zone(scaleMax, "High", "bg-slate-500"),
  ];
  const [verdictLabel, verdictColorClass] =
    value < 7 ? ["Low", "text-slate-300"] : value < 15 ? ["Moderate", "text-slate-300"] : ["High", "text-slate-300"];
  return {
    sentence: `Downside deviation of ${formatNumber(value)}% — only the down-moves counted, unlike volatility above which counts both directions.`,
    verdictLabel,
    verdictColorClass,
    scaleMin,
    scaleMax,
    zones,
  };
}

export function interpretUpsideCapture(value: number | null): MetricInterpretation | null {
  if (value === null) return null;
  const scaleMin = 0;
  const scaleMax = 200;
  const zones = [
    zone(80, "Low", "bg-slate-700"),
    zone(100, "Partial", "bg-slate-600"),
    zone(130, "Full+", "bg-emerald-900/60"),
    zone(scaleMax, "Amplified", "bg-emerald-600/60"),
  ];
  const verdictLabel = value < 100 ? "Partial" : "Full+";
  const verdictColorClass = "text-slate-300";
  const read =
    value < 100
      ? `captured only ${formatNumber(value, 0)}% of the benchmark's gains in up markets`
      : `captured ${formatNumber(value, 0)}% of the benchmark's gains in up markets — more than the benchmark itself moved`;
  return {
    sentence: `Upside capture of ${formatNumber(value, 1)}% — ${read}.`,
    verdictLabel,
    verdictColorClass,
    scaleMin,
    scaleMax,
    zones,
  };
}

export function interpretDownsideCapture(value: number | null): MetricInterpretation | null {
  if (value === null) return null;
  const scaleMin = 0;
  const scaleMax = 200;
  const zones = [
    zone(70, "Defensive", "bg-emerald-600/60"),
    zone(100, "Good", "bg-emerald-900/60"),
    zone(130, "Fair", "bg-amber-900/60"),
    zone(scaleMax, "Poor", "bg-rose-900/60"),
  ];
  const [verdictLabel, verdictColorClass, read] =
    value < 70
      ? ["Defensive", "text-emerald-400", "held up well in down markets, losing much less than the benchmark"]
      : value < 100
        ? ["Good", "text-emerald-400", "lost less than the benchmark in down markets"]
        : value < 130
          ? ["Fair", "text-amber-400", "lost roughly as much as, or slightly more than, the benchmark in down markets"]
          : ["Poor", "text-rose-400", "lost meaningfully more than the benchmark in down markets"];
  return {
    sentence: `Downside capture of ${formatNumber(value, 1)}% — ${read}.`,
    verdictLabel,
    verdictColorClass,
    scaleMin,
    scaleMax,
    zones,
  };
}

export function interpretBeta(value: number | null): MetricInterpretation | null {
  if (value === null) return null;
  const scaleMin = 0;
  const scaleMax = 2;
  const zones = [
    zone(0.85, "Defensive", "bg-slate-700"),
    zone(1.15, "Market-like", "bg-slate-600"),
    zone(scaleMax, "Amplified", "bg-slate-500"),
  ];
  const [verdictLabel, verdictColorClass, read] =
    value < 0.85
      ? ["Defensive", "text-slate-300", "tends to move less than the benchmark, in both directions"]
      : value < 1.15
        ? ["Market-like", "text-slate-300", "tends to move roughly in line with the benchmark"]
        : ["Amplified", "text-slate-300", "tends to move more than the benchmark, in both directions"];
  return {
    sentence: `Beta of ${formatNumber(value)} — ${read}.`,
    verdictLabel,
    verdictColorClass,
    scaleMin,
    scaleMax,
    zones,
  };
}

export function interpretJensenAlpha(value: number | null): MetricInterpretation | null {
  if (value === null) return null;
  const scaleMin = -8;
  const scaleMax = 8;
  const zones = [
    zone(-2, "Poor", "bg-rose-900/60"),
    zone(0, "Below Average", "bg-amber-900/60"),
    zone(2, "Good", "bg-emerald-900/60"),
    zone(scaleMax, "Excellent", "bg-emerald-600/60"),
  ];
  const [verdictLabel, verdictColorClass, read] =
    value < -2
      ? ["Poor", "text-rose-400", "underperformed what its risk level should have earned"]
      : value < 0
        ? ["Below Average", "text-amber-400", "slightly underperformed what its risk level should have earned"]
        : value < 2
          ? ["Good", "text-emerald-400", "outperformed what its risk level should have earned"]
          : ["Excellent", "text-emerald-400", "meaningfully outperformed what its risk level should have earned"];
  return {
    sentence: `Jensen's alpha of ${formatPct(value)} — ${read}, on a risk-adjusted (CAPM) basis.`,
    verdictLabel,
    verdictColorClass,
    scaleMin,
    scaleMax,
    zones,
  };
}

export function interpretMaxDrawdown(value: number | null): MetricInterpretation | null {
  if (value === null) return null;
  // Drawdown is always <= 0; the scale/zones work in magnitude (0 to 60)
  // and the caller passes the raw negative value — see ScalarScaleBar's
  // own clamp for how a magnitude scale reads a negative input.
  const scaleMin = -60;
  const scaleMax = 0;
  const zones = [
    zone(-40, "Extreme", "bg-rose-600/60"),
    zone(-25, "Severe", "bg-rose-900/60"),
    zone(-10, "Moderate", "bg-amber-900/60"),
    zone(scaleMax, "Mild", "bg-emerald-900/60"),
  ];
  const [verdictLabel, verdictColorClass, read] =
    value < -40
      ? ["Extreme", "text-rose-400", "an investor at the worst possible entry point lost well over a third of their money before recovery began"]
      : value < -25
        ? ["Severe", "text-rose-400", "an investor at the worst possible entry point lost roughly a quarter to a third of their money before recovery began"]
        : value < -10
          ? ["Moderate", "text-amber-400", "an investor at the worst possible entry point saw a real but survivable dip before recovery began"]
          : ["Mild", "text-emerald-400", "the worst historical dip so far has been shallow"];
  return {
    sentence: `Peak-to-trough drawdown of ${formatPct(value)} — ${read}.`,
    verdictLabel,
    verdictColorClass,
    scaleMin,
    scaleMax,
    zones,
  };
}

export function interpretRollingReturns(
  distribution: RollingReturnDistribution,
  windowYears: number,
  beatRatePct: number | null,
): string {
  const { min, median, max } = distribution;
  if (min === null || max === null || median === null) {
    return `Not enough NAV history for a ${windowYears}-year rolling window yet.`;
  }
  const base = `Over rolling ${windowYears}-year holding periods, this fund's annualized return ranged from ${formatPct(min)} to ${formatPct(max)}, with a typical (median) outcome of ${formatPct(median)}.`;
  if (beatRatePct === null) return base;
  return `${base} It beat its benchmark in ${formatNumber(beatRatePct, 0)}% of those windows.`;
}

// Fund → Category → Benchmark context (product-upgrade brief Section 5):
// a neutral "the fund's X was higher/lower/about the same as Y" clause,
// never a verdict ("better"/"worse") — the reader draws their own
// conclusion from the comparison, this only states what the numbers show.
function neutralComparisonClause(
  fundValue: number,
  otherValue: number,
  metricNoun: string,
  contextName: string,
  { higherIsLarger = true }: { higherIsLarger?: boolean } = {},
): string {
  const diff = fundValue - otherValue;
  // Below this, the two numbers are close enough that "larger"/"smaller"
  // would overstate a difference that's really just noise.
  if (Math.abs(diff) < 0.05) {
    return `The fund's ${metricNoun} was about the same as ${contextName} during the analysed period.`;
  }
  const isLarger = higherIsLarger ? diff > 0 : diff < 0;
  return `The fund experienced a ${isLarger ? "larger" : "smaller"} ${metricNoun} than ${contextName} during the analysed period.`;
}

export function drawdownContextSentence(
  fundValue: number,
  categoryAvg: number | null,
  categoryLabel: string,
  benchmarkValue: number | null,
  benchmarkName: string | null,
): string | null {
  const clauses: string[] = [];
  // Drawdown is a negative percentage — a numerically *lower* (more
  // negative) fund value is the *larger* drawdown, the opposite of CAGR/
  // volatility's plain "higher number reads as larger" convention.
  if (categoryAvg !== null) {
    clauses.push(
      neutralComparisonClause(fundValue, categoryAvg, "historical maximum drawdown", `its ${categoryLabel} category average`, {
        higherIsLarger: false,
      }),
    );
  }
  if (benchmarkValue !== null && benchmarkName !== null) {
    clauses.push(
      neutralComparisonClause(fundValue, benchmarkValue, "historical maximum drawdown", `its benchmark, ${benchmarkName}`, {
        higherIsLarger: false,
      }),
    );
  }
  return clauses.length > 0 ? clauses.join(" ") : null;
}

export function cagrContextSentence(
  fundValue: number,
  categoryAvg: number | null,
  categoryLabel: string,
  benchmarkValue: number | null,
  benchmarkName: string | null,
): string | null {
  const clauses: string[] = [];
  if (categoryAvg !== null) {
    clauses.push(neutralComparisonClause(fundValue, categoryAvg, "3-year annualised return", `its ${categoryLabel} category average`));
  }
  if (benchmarkValue !== null && benchmarkName !== null) {
    clauses.push(neutralComparisonClause(fundValue, benchmarkValue, "3-year annualised return", `its benchmark, ${benchmarkName}`));
  }
  return clauses.length > 0 ? clauses.join(" ") : null;
}

export function volatilityContextSentence(
  fundValue: number,
  categoryAvg: number | null,
  categoryLabel: string,
  benchmarkValue: number | null,
  benchmarkName: string | null,
): string | null {
  const clauses: string[] = [];
  if (categoryAvg !== null) {
    clauses.push(neutralComparisonClause(fundValue, categoryAvg, "volatility", `its ${categoryLabel} category average`));
  }
  if (benchmarkValue !== null && benchmarkName !== null) {
    clauses.push(neutralComparisonClause(fundValue, benchmarkValue, "volatility", `its benchmark, ${benchmarkName}`));
  }
  return clauses.length > 0 ? clauses.join(" ") : null;
}
