/** One line of secondary text in place of a flat "—" for the benchmark
 * column, when we know *why* it's unavailable — never displayed as if it
 * were color- or icon-coded; the words carry the whole distinction. Falls
 * back to a generic label for an unrecognized reason code rather than
 * showing nothing. */
const BENCHMARK_REASON_LABELS: Record<string, string> = {
  no_benchmark_mapped: "Benchmark unavailable",
  data_unavailable: "Data unavailable",
  insufficient_history: "Insufficient history",
};

/** Fund → Category → Benchmark context (product-upgrade brief Section 5)
 * for a single metric — the same figure shown three ways, plus a neutral
 * sentence stating what the comparison shows. Never a score, ranking, or
 * verdict ("best"/"winner") — just the evidence, laid out for the reader
 * to interpret themselves. Renders nothing when there's no category or
 * benchmark figure to compare against (a fund alone in its category, or
 * with no linked benchmark), rather than showing a comparison of one. */
export function CategoryBenchmarkRow({
  label,
  fundValue,
  categoryValue,
  categoryLabel,
  benchmarkValue,
  benchmarkName,
  benchmarkReason,
  formatValue,
  interpretation,
}: {
  label: string;
  fundValue: number;
  categoryValue: number | null;
  categoryLabel: string;
  benchmarkValue: number | null;
  benchmarkName: string | null;
  /** "no_benchmark_mapped" | "data_unavailable" | "insufficient_history" | null — see BENCHMARK_REASON_LABELS. */
  benchmarkReason?: string | null;
  formatValue: (v: number) => string;
  interpretation: string | null;
}) {
  if (categoryValue === null && benchmarkValue === null) return null;

  return (
    <div className="rounded-lg border border-slate-800 p-4 space-y-3">
      <h3 className="text-xs uppercase tracking-wide text-slate-500">{label}: Fund vs. Category vs. Benchmark</h3>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <div className="text-xs text-slate-500">Fund</div>
          <div className="font-mono tabular-nums font-semibold text-slate-100 mt-0.5">{formatValue(fundValue)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Category Avg</div>
          <div className="font-mono tabular-nums font-semibold text-slate-300 mt-0.5">
            {categoryValue !== null ? formatValue(categoryValue) : "—"}
          </div>
          <div className="text-[11px] text-slate-600 mt-0.5">{categoryLabel}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Benchmark</div>
          <div className="font-mono tabular-nums font-semibold text-slate-300 mt-0.5">
            {benchmarkValue !== null
              ? formatValue(benchmarkValue)
              : benchmarkReason
                ? BENCHMARK_REASON_LABELS[benchmarkReason] ?? "—"
                : "—"}
          </div>
          {benchmarkName && <div className="text-[11px] text-slate-600 mt-0.5">{benchmarkName}</div>}
        </div>
      </div>
      {interpretation && <p className="text-sm text-slate-400">{interpretation}</p>}
    </div>
  );
}
