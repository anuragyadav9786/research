import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { ApiError, getFundScreener } from "@/lib/api";
import { formatDate, formatPct, signColorClass } from "@/lib/format";
import { SCREENER_PERIODS, type ScreenerPeriod } from "@/types/fund";

export const metadata = { title: "Fund Screener — ThinkFin" };

const PERIOD_LABELS: Record<ScreenerPeriod, string> = {
  "1m": "1 Month", "3m": "3 Month", "6m": "6 Month", "1y": "1 Year", "3y": "3 Year", "5y": "5 Year",
};

function isScreenerPeriod(value: string | undefined): value is ScreenerPeriod {
  return !!value && (SCREENER_PERIODS as readonly string[]).includes(value);
}

export default async function FundScreenerPage({
  searchParams,
}: {
  searchParams: Promise<{ sort_by?: string; sort_dir?: string }>;
}) {
  const { sort_by, sort_dir } = await searchParams;
  const sortBy: ScreenerPeriod = isScreenerPeriod(sort_by) ? sort_by : "1y";
  const sortDir: "asc" | "desc" = sort_dir === "asc" ? "asc" : "desc";

  let error: string | null = null;
  const screener = await getFundScreener(sortBy, sortDir).catch((err) => {
    error = err instanceof ApiError ? err.message : "Could not load the fund screener.";
    return null;
  });

  function sortLink(period: ScreenerPeriod) {
    const nextDir = sortBy === period && sortDir === "desc" ? "asc" : "desc";
    return `/research/screener?sort_by=${period}&sort_dir=${nextDir}`;
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="research" />
      <main className="max-w-6xl mx-auto px-4 py-8 space-y-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Fund Screener</h1>
          <p className="text-sm text-slate-500 mt-1 max-w-2xl">
            Real, historical returns across common lookback windows — sortable, not a ranking. Every figure comes
            from this fund&rsquo;s own NAV history; a blank cell means there isn&rsquo;t enough history yet for that
            window, never a guessed or hidden number.
          </p>
        </div>

        {error && <p className="text-sm text-rose-400">{error}</p>}

        {screener && (
          <>
            <p className="text-xs text-slate-500">
              {screener.total_eligible} funds covered
              {screener.as_of_date && <> · as of {formatDate(screener.as_of_date)}</>}
            </p>

            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900/60 text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="px-3 py-2 font-medium">Fund</th>
                    <th className="px-3 py-2 font-medium">Category</th>
                    {SCREENER_PERIODS.map((period) => (
                      <th key={period} className="px-3 py-2 font-medium text-right">
                        <Link
                          href={sortLink(period)}
                          className={`hover:text-slate-300 whitespace-nowrap ${sortBy === period ? "text-indigo-400" : ""}`}
                        >
                          {PERIOD_LABELS[period]}
                          {sortBy === period && <span className="ml-1">{sortDir === "desc" ? "↓" : "↑"}</span>}
                        </Link>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {screener.items.map((item) => (
                    <tr key={item.id} className="border-b border-slate-900 last:border-0 hover:bg-slate-900/40">
                      <td className="px-3 py-2">
                        <Link href={`/research/${item.id}`} className="text-slate-200 hover:text-indigo-300">
                          {item.scheme_name}
                        </Link>
                        <div className="text-xs text-slate-600">{item.amc_name}</div>
                      </td>
                      <td className="px-3 py-2 text-slate-500">{item.category}</td>
                      {SCREENER_PERIODS.map((period) => {
                        const cell = item.returns[period];
                        return (
                          <td key={period} className="px-3 py-2 text-right font-mono tabular-nums">
                            {cell.status === "VALID" && cell.return_pct !== null ? (
                              <span className={signColorClass(cell.return_pct)}>{formatPct(cell.return_pct)}</span>
                            ) : (
                              <span className="text-slate-700">—</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="text-xs text-slate-600">{screener.disclaimer}</p>
          </>
        )}
      </main>
    </div>
  );
}
