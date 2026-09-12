import { formatNumber } from "@/lib/format";
import type { HoldingItem } from "@/types/portfolio";

const MARKET_CAP_LABELS: Record<string, string> = {
  large_cap: "Large Cap",
  mid_cap: "Mid Cap",
  small_cap: "Small Cap",
  other: "Other",
};

export function HoldingsTable({ holdings }: { holdings: HoldingItem[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-left text-xs uppercase tracking-wide text-neutral-500">
            <th className="px-4 py-2 font-medium">#</th>
            <th className="px-4 py-2 font-medium">Security</th>
            <th className="px-4 py-2 font-medium">Sector</th>
            <th className="px-4 py-2 font-medium">Market Cap</th>
            <th className="px-4 py-2 font-medium text-right">Weight</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-900">
          {holdings.map((h) => (
            <tr key={h.rank}>
              <td className="px-4 py-2 text-neutral-500">{h.rank}</td>
              <td className="px-4 py-2">{h.security_name}</td>
              <td className="px-4 py-2 text-neutral-400">{h.sector?.replace(/^Sample: /, "") ?? "—"}</td>
              <td className="px-4 py-2 text-neutral-400">
                {h.market_cap_category ? (MARKET_CAP_LABELS[h.market_cap_category] ?? h.market_cap_category) : "—"}
              </td>
              <td className="px-4 py-2 text-right font-medium">{formatNumber(h.weight_pct, 2)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
