import Link from "next/link";

import { formatDate, formatNumber } from "@/lib/format";
import type { HolderRow } from "@/types/security";

export function HoldersTable({ holders }: { holders: HolderRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-4 py-2 font-medium">Scheme</th>
            <th className="px-4 py-2 font-medium">AMC</th>
            <th className="px-4 py-2 font-medium">As Of</th>
            <th className="px-4 py-2 font-medium text-right">Weight</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {holders.map((h) => (
            <tr key={h.scheme_id} className="hover:bg-slate-900 transition-colors">
              <td className="px-4 py-2">
                <Link href={`/research/${h.scheme_id}`} className="hover:text-indigo-400">
                  {h.scheme_name}
                </Link>
              </td>
              <td className="px-4 py-2 text-slate-400">{h.amc_name}</td>
              <td className="px-4 py-2 text-slate-400">{formatDate(h.as_of_date)}</td>
              <td className="px-4 py-2 text-right font-medium">{formatNumber(h.weight_pct, 2)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
