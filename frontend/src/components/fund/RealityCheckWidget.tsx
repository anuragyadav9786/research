import Link from "next/link";

import { formatPct } from "@/lib/format";
import { DistributionBar } from "@/components/fund/DistributionBar";
import { BenchmarkDeltaBadge, type BenchmarkMetrics, deltaVsBenchmark, safetyMarginVsBenchmark } from "@/components/fund/BenchmarkDeltaBadge";
import type { RollingReturnDistribution } from "@/types/fund";

export interface RealityCheckFund {
  id: number;
  name: string;
  category: string;
  cagr3y: number | null;
  medianRolling3y: number | null;
  maxDrawdown: number | null;
  distribution: RollingReturnDistribution;
}

type RowKind = "return" | "drawdown";

/** Which side (if either) wins a row: higher is better for returns,
 * shallower (smaller magnitude) drawdown is better for risk. Null when
 * either side is missing or the two values tie — never guessed. */
function winnerOf(a: number | null, b: number | null, kind: RowKind): "a" | "b" | null {
  if (a === null || b === null || a === b) return null;
  if (kind === "drawdown") return Math.abs(a) < Math.abs(b) ? "a" : "b";
  return a > b ? "a" : "b";
}

/** Real numbers only — every figure here comes from this platform's own
 * computed returns/rolling-returns/drawdown for two real, currently
 * onboarded funds, not placeholder data. Compares fund-to-fund directly,
 * plus (when `benchmark` is supplied) against a real passive index fund —
 * see BenchmarkDeltaBadge.tsx for why an index fund stands in for a raw
 * benchmark index. */
export function RealityCheckWidget({
  fundA,
  fundB,
  benchmark,
}: {
  fundA: RealityCheckFund;
  fundB: RealityCheckFund;
  benchmark?: BenchmarkMetrics | null;
}) {
  const rows: {
    label: string;
    help: string;
    a: number | null;
    b: number | null;
    kind: RowKind;
    benchmarkValue: number | null;
  }[] = [
    {
      label: "3Y Point-to-Point CAGR",
      help: "Annualized return from a single fixed start date 3 years ago to today — sensitive to whichever day you happen to measure from.",
      a: fundA.cagr3y,
      b: fundB.cagr3y,
      kind: "return",
      benchmarkValue: benchmark?.cagr3y ?? null,
    },
    {
      label: "3Y Rolling CAGR (Median)",
      help: "The typical 3-year annualized return across every possible 3-year window in the fund's history, not just one snapshot — a steadier read on consistency.",
      a: fundA.medianRolling3y,
      b: fundB.medianRolling3y,
      kind: "return",
      benchmarkValue: benchmark?.medianRolling3y ?? null,
    },
    {
      label: "Max Drawdown (Since Inception)",
      help: "The largest peak-to-trough decline the fund has ever suffered — a measure of how much you could have lost at the worst possible moment.",
      a: fundA.maxDrawdown,
      b: fundB.maxDrawdown,
      kind: "drawdown",
      benchmarkValue: benchmark?.maxDrawdown ?? null,
    },
  ];

  const distMins = [fundA.distribution.min, fundB.distribution.min].filter((v): v is number => v !== null);
  const distMaxes = [fundA.distribution.max, fundB.distribution.max].filter((v): v is number => v !== null);
  const sharedScale =
    distMins.length === 2 && distMaxes.length === 2
      ? { scaleMin: Math.min(...distMins), scaleMax: Math.max(...distMaxes) }
      : {};

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">See What Most Portals Hide</h2>
        <p className="text-sm text-slate-400 mt-1">
          Compare rolling-return consistency and downside protection, not just a single point-to-point CAGR —
          computed live from these two funds&apos; real NAV history.
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-800">
              <th className="pb-2 font-normal">Metric</th>
              <th className="pb-2 font-normal text-right">{fundA.name}</th>
              <th className="pb-2 font-normal text-right">{fundB.name}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {rows.map((row) => {
              const winner = winnerOf(row.a, row.b, row.kind);
              return (
                <tr key={row.label}>
                  <td className="py-2.5 text-slate-400">
                    <span
                      className="underline decoration-dotted decoration-slate-600 underline-offset-4 cursor-help"
                      title={row.help}
                    >
                      {row.label}
                    </span>
                  </td>
                  <td className={`py-2.5 px-2 text-right rounded ${winner === "a" ? "bg-emerald-500/10" : ""}`}>
                    <div className={`font-mono tabular-nums ${winner === "a" ? "text-emerald-300 font-semibold" : "text-slate-100"}`}>
                      {formatPct(row.a)}
                      {winner === "a" && <span className="ml-1 text-emerald-400">✓</span>}
                    </div>
                    {benchmark && (
                      <BenchmarkDeltaBadge
                        className="mt-1 justify-end"
                        delta={
                          row.kind === "drawdown"
                            ? safetyMarginVsBenchmark(row.a, row.benchmarkValue)
                            : deltaVsBenchmark(row.a, row.benchmarkValue)
                        }
                        kind={row.kind}
                        benchmarkName={benchmark.name}
                      />
                    )}
                  </td>
                  <td className={`py-2.5 px-2 text-right rounded ${winner === "b" ? "bg-emerald-500/10" : ""}`}>
                    <div className={`font-mono tabular-nums ${winner === "b" ? "text-emerald-300 font-semibold" : "text-slate-100"}`}>
                      {formatPct(row.b)}
                      {winner === "b" && <span className="ml-1 text-emerald-400">✓</span>}
                    </div>
                    {benchmark && (
                      <BenchmarkDeltaBadge
                        className="mt-1 justify-end"
                        delta={
                          row.kind === "drawdown"
                            ? safetyMarginVsBenchmark(row.b, row.benchmarkValue)
                            : deltaVsBenchmark(row.b, row.benchmarkValue)
                        }
                        kind={row.kind}
                        benchmarkName={benchmark.name}
                      />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">
            {fundA.name} — 3Y rolling return spread
          </p>
          <DistributionBar distribution={fundA.distribution} {...sharedScale} />
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">
            {fundB.name} — 3Y rolling return spread
          </p>
          <DistributionBar distribution={fundB.distribution} {...sharedScale} />
        </div>
      </div>

      <Link
        href={`/research/compare?a=${fundA.id}&b=${fundB.id}`}
        className="inline-flex items-center gap-1.5 rounded-md bg-indigo-500 text-white font-medium text-sm px-4 py-2 hover:bg-indigo-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        Compare with Your Own Fund →
      </Link>
    </div>
  );
}
