export interface BenchmarkMetrics {
  name: string;
  cagr3y: number | null;
  medianRolling3y: number | null;
  maxDrawdown: number | null;
}

/** For return-type metrics (higher is better): fund value minus benchmark
 * value, or null if either side is unavailable — never fabricated. */
export function deltaVsBenchmark(fundValue: number | null, benchmarkValue: number | null): number | null {
  if (fundValue == null || benchmarkValue == null) return null;
  return fundValue - benchmarkValue;
}

/** For max drawdown (both values negative, smaller magnitude is safer):
 * positive result means the fund's drawdown was shallower (safer) than
 * the benchmark's by that many percentage points; negative means deeper
 * (riskier). */
export function safetyMarginVsBenchmark(fundDrawdown: number | null, benchmarkDrawdown: number | null): number | null {
  if (fundDrawdown == null || benchmarkDrawdown == null) return null;
  return Math.abs(benchmarkDrawdown) - Math.abs(fundDrawdown);
}

/** Small muted pill showing a fund metric's real delta against a real
 * benchmark index fund (see docs/analytics-methodology.md — an index
 * fund's growth-plan NAV reflects dividends reinvested, unlike a raw
 * price index, and is just another real fund in this same dataset).
 * Renders nothing when the delta isn't computable — never a fabricated
 * placeholder number. */
export function BenchmarkDeltaBadge({
  delta,
  kind,
  benchmarkName,
  className = "",
}: {
  delta: number | null;
  kind: "return" | "drawdown";
  benchmarkName: string;
  className?: string;
}) {
  if (delta == null) return null;

  const favorable = delta >= 0;
  const magnitude = Math.abs(delta).toFixed(1);
  const label =
    kind === "drawdown"
      ? `${magnitude}% ${favorable ? "safer" : "riskier"} than ${benchmarkName}`
      : `${favorable ? "+" : "-"}${magnitude}% vs ${benchmarkName}`;

  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${
        favorable ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"
      } ${className}`}
    >
      {label}
    </span>
  );
}
