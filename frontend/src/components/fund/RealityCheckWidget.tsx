import Link from "next/link";

import { formatPct } from "@/lib/format";
import { DistributionBar } from "@/components/fund/DistributionBar";
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

/** Real numbers only — every figure here comes from this platform's own
 * computed returns/rolling-returns/drawdown for two real, currently
 * onboarded funds, not placeholder data. Compares fund-to-fund rather
 * than fund-to-benchmark since no real benchmark (index) history exists
 * in this platform yet — see docs/analytics-methodology.md. */
export function RealityCheckWidget({ fundA, fundB }: { fundA: RealityCheckFund; fundB: RealityCheckFund }) {
  const rows: { label: string; a: number | null; b: number | null; digits?: number }[] = [
    { label: "3Y Point-to-Point CAGR", a: fundA.cagr3y, b: fundB.cagr3y },
    { label: "3Y Rolling CAGR (Median)", a: fundA.medianRolling3y, b: fundB.medianRolling3y },
    { label: "Max Drawdown (Since Inception)", a: fundA.maxDrawdown, b: fundB.maxDrawdown },
  ];

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
            {rows.map((row) => (
              <tr key={row.label}>
                <td className="py-2.5 text-slate-400">{row.label}</td>
                <td className="py-2.5 text-right font-mono tabular-nums text-slate-100">{formatPct(row.a)}</td>
                <td className="py-2.5 text-right font-mono tabular-nums text-slate-100">{formatPct(row.b)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid sm:grid-cols-2 gap-6">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">
            {fundA.name} — 3Y rolling return spread
          </p>
          <DistributionBar distribution={fundA.distribution} />
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">
            {fundB.name} — 3Y rolling return spread
          </p>
          <DistributionBar distribution={fundB.distribution} />
        </div>
      </div>

      <Link
        href={`/research/compare?a=${fundA.id}&b=${fundB.id}`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-400 hover:text-indigo-300"
      >
        Compare with Your Own Fund →
      </Link>
    </div>
  );
}
