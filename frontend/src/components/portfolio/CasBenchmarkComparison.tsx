import { Disclosure } from "@/components/fund/Disclosure";
import { StatCard } from "@/components/fund/StatCard";
import { formatDate, formatPct, signColorClass } from "@/lib/format";
import type { CASBenchmarkComparison as CASBenchmarkComparisonType } from "@/types/cas";

/** Benchmarks the portfolio's own blended return (Return Consistency's
 * Time-Weighted Return, above) against a value-weighted blend of each
 * matched holding's own benchmark TRI return, over the identical window
 * — see app/services/cas_portfolio_service.py's _portfolio_benchmark_summary.
 * Renders nothing when unavailable (no priced schemes, or none of them
 * have a usable benchmark), rather than a card full of "N/A". */
export function CasBenchmarkComparison({ comparison }: { comparison: CASBenchmarkComparisonType }) {
  if (!comparison.available) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-xs uppercase tracking-wide text-slate-500">Vs. Benchmark</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Portfolio Return"
          value={comparison.portfolio_return_pct !== null ? formatPct(comparison.portfolio_return_pct) : "N/A"}
          valueClassName={comparison.portfolio_return_pct !== null ? signColorClass(comparison.portfolio_return_pct) : "text-slate-600"}
          hint={`${formatDate(comparison.start_date)} to ${formatDate(comparison.end_date)}`}
        />
        <StatCard
          label="Benchmark Return"
          value={comparison.benchmark_blended_return_pct !== null ? formatPct(comparison.benchmark_blended_return_pct) : "N/A"}
          valueClassName={
            comparison.benchmark_blended_return_pct !== null ? signColorClass(comparison.benchmark_blended_return_pct) : "text-slate-600"
          }
          hint={comparison.benchmark_names.length > 0 ? comparison.benchmark_names.join(", ") : undefined}
        />
        <StatCard
          label="Excess Return"
          value={comparison.excess_return_pct !== null ? formatPct(comparison.excess_return_pct) : "N/A"}
          valueClassName={comparison.excess_return_pct !== null ? signColorClass(comparison.excess_return_pct) : "text-slate-600"}
          hint="Portfolio minus benchmark, same window"
        />
        <StatCard
          label="Coverage"
          value={comparison.benchmark_coverage_pct !== null ? `${comparison.benchmark_coverage_pct.toFixed(0)}%` : "N/A"}
          hint="Of current value with a usable benchmark"
        />
      </div>
      <Disclosure label="How is this calculated?">
        <p className="text-sm text-slate-400">
          Each matched holding&rsquo;s own benchmark return over the exact same window is blended by current
          portfolio weight. A holding with no mapped benchmark, or whose benchmark has no price history for this
          window, is excluded from the blend rather than assumed to track the portfolio — Coverage shows how much
          of the portfolio&rsquo;s value the comparison actually reflects.
        </p>
      </Disclosure>
    </div>
  );
}
