import { formatPct, formatRupees, signColorClass } from "@/lib/format";
import type { CASSchemeOverview } from "@/types/cas";

/** Portfolio Analysis §15 (Fund Contribution Analysis): how each matched
 * scheme's own weight, return, and share of total gain break down —
 * distinct from Portfolio Structure (§7/§8), which is about allocation,
 * not performance. Sorted by weight so the largest holdings read first. */
export function CasFundContribution({ perScheme }: { perScheme: CASSchemeOverview[] }) {
  const rows = [...perScheme].sort((a, b) => (b.weight_pct ?? -1) - (a.weight_pct ?? -1));

  return (
    <div>
      <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Fund Contribution</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-900">
              <th className="py-1.5 pr-3 font-normal">Scheme</th>
              <th className="py-1.5 px-3 font-normal text-right">Weight</th>
              <th className="py-1.5 px-3 font-normal text-right">Fund XIRR</th>
              <th className="py-1.5 px-3 font-normal text-right">Gain</th>
              <th className="py-1.5 pl-3 font-normal text-right">Share of Gain</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.isin} className="border-b border-slate-900/60 last:border-0">
                <td className="py-1.5 pr-3 text-slate-300">{s.scheme_name}</td>
                <td className="py-1.5 px-3 text-right font-mono tabular-nums text-slate-300">
                  {s.weight_pct !== null ? `${s.weight_pct.toFixed(1)}%` : "—"}
                </td>
                <td className={`py-1.5 px-3 text-right font-mono tabular-nums ${signColorClass(s.scheme_xirr_pct)}`}>
                  {s.scheme_xirr_pct !== null ? formatPct(s.scheme_xirr_pct) : "N/A"}
                </td>
                <td className={`py-1.5 px-3 text-right font-mono tabular-nums ${signColorClass(s.gain)}`}>
                  {s.gain !== null ? formatRupees(s.gain) : "Unpriced holding"}
                </td>
                <td className={`py-1.5 pl-3 text-right font-mono tabular-nums ${signColorClass(s.contribution_to_gain_pct)}`}>
                  {s.contribution_to_gain_pct !== null ? formatPct(s.contribution_to_gain_pct) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-600 mt-1.5">
        Fund XIRR is this scheme&rsquo;s own money-weighted return, in isolation — it can differ from the
        portfolio-wide XIRR above because of when and how much was invested in each fund.
      </p>
    </div>
  );
}
