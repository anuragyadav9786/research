import { formatRupees } from "@/lib/format";
import type { CASTransactionActivity as CASTransactionActivityData } from "@/types/cas";

const TRANSACTION_TYPE_LABELS: Record<string, string> = {
  PURCHASE: "Lumpsum Purchase",
  SIP: "SIP Installment",
  REDEMPTION: "Redemption",
  SWP: "SWP",
  SWITCH_IN: "Switch In",
  SWITCH_OUT: "Switch Out",
  STP_IN: "STP In",
  STP_OUT: "STP Out",
  DIVIDEND: "Dividend Payout",
  DIVIDEND_REINVESTMENT: "Dividend Reinvestment",
  BONUS: "Bonus Units",
  REVERSAL: "Reversal",
  OTHER: "Other",
};

/** Portfolio Analysis §14 (redemption/switching behavior): how often, and
 * for how much, the investor actually transacted — one row per
 * transaction type that occurred at least once, across every matched
 * scheme. Purely descriptive: no framing of any category as good or bad,
 * and switches/STP are shown here (they're real activity) even though
 * they're excluded from invested/XIRR figures elsewhere as internal
 * transfers, not external cash flow. */
export function CasTransactionActivity({ activity }: { activity: CASTransactionActivityData[] }) {
  if (activity.length === 0) return null;

  return (
    <div>
      <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Transaction Activity</h3>
      <ul className="text-sm text-slate-300 divide-y divide-slate-900/60">
        {activity.map((row) => (
          <li key={row.transaction_type} className="flex justify-between py-1.5">
            <span>
              {TRANSACTION_TYPE_LABELS[row.transaction_type] ?? row.transaction_type}
              <span className="text-slate-600"> · {row.count}×</span>
            </span>
            <span className="font-mono tabular-nums text-slate-400">{formatRupees(row.total_amount)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
