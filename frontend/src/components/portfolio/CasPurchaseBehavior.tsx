import { formatDate, formatNav } from "@/lib/format";
import type { CASSchemeOverview } from "@/types/cas";

function purchaseMixLabel(behavior: CASSchemeOverview["purchase_behavior"]): string {
  const { lumpsum_count, sip_installment_count } = behavior;
  if (lumpsum_count > 0 && sip_installment_count > 0) return `${lumpsum_count} lumpsum + ${sip_installment_count} SIP`;
  if (sip_installment_count > 0) return `${sip_installment_count} SIP installment${sip_installment_count === 1 ? "" : "s"}`;
  return `${lumpsum_count} lumpsum`;
}

/** Portfolio Analysis §13: this scheme's own purchase/NAV behavior — how
 * many purchases, lumpsum vs. SIP, over what span, and at what NAV range.
 * Purely descriptive (no framing of any figure as good or bad timing),
 * consistent with the module's no-buy/sell-engine constraint. Skips a
 * scheme with zero purchase-type transactions (e.g. everything arrived
 * via switch-in) rather than a row full of dashes. */
export function CasPurchaseBehavior({ perScheme }: { perScheme: CASSchemeOverview[] }) {
  const rows = perScheme.filter((s) => s.purchase_behavior.purchase_count > 0);
  if (rows.length === 0) return null;

  return (
    <div>
      <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Purchase Activity</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-900">
              <th className="py-1.5 pr-3 font-normal">Scheme</th>
              <th className="py-1.5 px-3 font-normal">Purchases</th>
              <th className="py-1.5 px-3 font-normal">First → Latest</th>
              <th className="py-1.5 pl-3 font-normal text-right">NAV Range Paid</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const b = s.purchase_behavior;
              return (
                <tr key={s.isin} className="border-b border-slate-900/60 last:border-0">
                  <td className="py-1.5 pr-3 text-slate-300">{s.scheme_name}</td>
                  <td className="py-1.5 px-3 text-slate-400">{purchaseMixLabel(b)}</td>
                  <td className="py-1.5 px-3 font-mono tabular-nums text-slate-400">
                    {formatDate(b.first_purchase_date)}
                    {b.first_purchase_date !== b.latest_purchase_date && <> → {formatDate(b.latest_purchase_date)}</>}
                  </td>
                  <td className="py-1.5 pl-3 text-right font-mono tabular-nums text-slate-300">
                    {b.lowest_purchase_nav !== null && b.lowest_purchase_nav !== b.highest_purchase_nav
                      ? `${formatNav(b.lowest_purchase_nav)} – ${formatNav(b.highest_purchase_nav)}`
                      : formatNav(b.lowest_purchase_nav)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
