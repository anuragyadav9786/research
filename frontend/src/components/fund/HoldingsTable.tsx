import Link from "next/link";

import { formatNumber } from "@/lib/format";
import type { HoldingItem } from "@/types/portfolio";

const MARKET_CAP_LABELS: Record<string, string> = {
  large_cap: "Large Cap",
  mid_cap: "Mid Cap",
  small_cap: "Small Cap",
  other: "Other",
};

const INSTRUMENT_TYPE_LABELS: Record<string, string> = {
  equity: "Equity",
  debt: "Debt",
  government_security: "G-Sec",
  securitised_debt: "Securitised Debt",
  money_market: "Money Market",
  mutual_fund_unit: "Mutual Fund Unit",
  reit_invit: "REIT/InvIT",
  foreign_security: "Foreign Security",
  cash_equivalent: "Cash Equivalent",
  other: "Other",
};

export function HoldingsTable({ holdings }: { holdings: HoldingItem[] }) {
  const showInstrumentType = holdings.some((h) => h.instrument_type !== null);
  const showCreditRating = holdings.some((h) => h.credit_rating !== null);
  const showYtm = holdings.some((h) => h.ytm_pct !== null);

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-4 py-2 font-medium">#</th>
            <th className="px-4 py-2 font-medium">Security</th>
            <th className="px-4 py-2 font-medium">Sector</th>
            <th className="px-4 py-2 font-medium">Market Cap</th>
            {showInstrumentType && <th className="px-4 py-2 font-medium">Instrument Type</th>}
            {showCreditRating && <th className="px-4 py-2 font-medium">Credit Rating</th>}
            {showYtm && <th className="px-4 py-2 font-medium text-right">YTM</th>}
            <th className="px-4 py-2 font-medium text-right">Weight</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {holdings.map((h) => (
            <tr key={h.rank}>
              <td className="px-4 py-2 text-slate-500">{h.rank}</td>
              <td className="px-4 py-2">
                <Link href={`/research/securities/${h.security_id}`} className="hover:text-indigo-400">
                  {h.security_name}
                </Link>
              </td>
              <td className="px-4 py-2 text-slate-400">{h.sector?.replace(/^Sample: /, "") ?? "—"}</td>
              <td className="px-4 py-2 text-slate-400">
                {h.market_cap_category ? (MARKET_CAP_LABELS[h.market_cap_category] ?? h.market_cap_category) : "—"}
              </td>
              {showInstrumentType && (
                <td className="px-4 py-2 text-slate-400">
                  {h.instrument_type ? (INSTRUMENT_TYPE_LABELS[h.instrument_type] ?? h.instrument_type) : "—"}
                </td>
              )}
              {showCreditRating && <td className="px-4 py-2 text-slate-400">{h.credit_rating ?? "—"}</td>}
              {showYtm && (
                <td className="px-4 py-2 text-right text-slate-400">
                  {h.ytm_pct !== null ? `${formatNumber(h.ytm_pct, 2)}%` : "—"}
                </td>
              )}
              <td className="px-4 py-2 text-right font-medium">{formatNumber(h.weight_pct, 2)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
