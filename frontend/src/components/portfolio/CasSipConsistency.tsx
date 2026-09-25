import type { CASSchemeOverview } from "@/types/cas";

/** Portfolio Analysis §13: how regularly each scheme's SIP installments
 * actually arrived, purely from the gaps between installment dates — never
 * against an assumed "should be monthly" cadence the CAS itself doesn't
 * state. Skips a scheme with no SIP installments (lumpsum-only) rather
 * than showing an empty card, and skips the whole section if nothing in
 * the portfolio has any SIP history. */
export function CasSipConsistency({ perScheme }: { perScheme: CASSchemeOverview[] }) {
  const rows = perScheme.filter((s) => s.sip_consistency !== null);
  if (rows.length === 0) return null;

  return (
    <div>
      <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">SIP Consistency</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-900">
              <th className="py-1.5 pr-3 font-normal">Scheme</th>
              <th className="py-1.5 px-3 font-normal text-right">Installments</th>
              <th className="py-1.5 px-3 font-normal text-right">Gap (avg / range)</th>
              <th className="py-1.5 pl-3 font-normal text-right">Consistency</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const sip = s.sip_consistency!;
              return (
                <tr key={s.isin} className="border-b border-slate-900/60 last:border-0">
                  <td className="py-1.5 pr-3 text-slate-300">{s.scheme_name}</td>
                  <td className="py-1.5 px-3 text-right font-mono tabular-nums text-slate-400">
                    {sip.installment_count}
                  </td>
                  <td className="py-1.5 px-3 text-right font-mono tabular-nums text-slate-400">
                    {sip.average_gap_days !== null
                      ? `${sip.average_gap_days}d (${sip.min_gap_days}–${sip.max_gap_days}d)`
                      : "—"}
                  </td>
                  <td className="py-1.5 pl-3 text-right font-mono tabular-nums text-slate-300">
                    {sip.gap_consistency_pct !== null ? `${sip.gap_consistency_pct}%` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-600 mt-1.5">
        Consistency compares how much installment gaps varied against their own average — 100% means every gap was
        identical. It isn&rsquo;t a judgment of the installment amounts or your investing discipline, just how evenly
        spaced they were.
      </p>
    </div>
  );
}
