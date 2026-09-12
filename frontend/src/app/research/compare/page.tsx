import Link from "next/link";

import { ApiError, getFundOverlap, listFunds } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/format";

const OVERLAP_LABELS: Record<string, string> = {
  low_overlap: "Low Overlap",
  moderate_overlap: "Moderate Overlap",
  high_overlap: "High Overlap",
};

export const metadata = { title: "Compare Funds — ThinkFin" };

export default async function CompareFundsPage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>;
}) {
  const { a, b } = await searchParams;
  const funds = await listFunds();

  const fundIdA = a ? Number(a) : undefined;
  const fundIdB = b ? Number(b) : undefined;
  const canCompare = fundIdA && fundIdB && fundIdA !== fundIdB;

  let overlapError: string | null = null;
  const overlap = canCompare ? await getFundOverlap(fundIdA, fundIdB).catch((err) => {
    overlapError = err instanceof ApiError ? err.message : "Could not load overlap data.";
    return null;
  }) : null;

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-8 py-4 flex items-center justify-between">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          ThinkFin
        </Link>
        <nav className="flex gap-6 text-sm text-neutral-400">
          <Link href="/" className="hover:text-neutral-100">Dashboard</Link>
          <Link href="/research" className="hover:text-neutral-100">Research</Link>
          <Link href="/research/compare" className="text-neutral-100">Compare</Link>
        </nav>
      </header>

      <main className="px-8 py-10 max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Fund Overlap</h1>
          <p className="text-neutral-400 text-sm mt-1">
            How much do two funds actually share — holdings, sectors, and return behaviour?
          </p>
        </div>

        <form method="get" className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="block text-xs uppercase tracking-wide text-neutral-500 mb-1">Fund A</span>
            <select
              name="a"
              defaultValue={a ?? ""}
              className="min-w-[220px] rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm"
            >
              <option value="" disabled>Select a fund…</option>
              {funds.map((f) => (
                <option key={f.id} value={f.id}>{f.scheme_name}</option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="block text-xs uppercase tracking-wide text-neutral-500 mb-1">Fund B</span>
            <select
              name="b"
              defaultValue={b ?? ""}
              className="min-w-[220px] rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm"
            >
              <option value="" disabled>Select a fund…</option>
              {funds.map((f) => (
                <option key={f.id} value={f.id}>{f.scheme_name}</option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="rounded-md border border-neutral-700 bg-neutral-800 px-4 py-2 text-sm hover:bg-neutral-700"
          >
            Compare
          </button>
        </form>

        {fundIdA && fundIdB && fundIdA === fundIdB && (
          <p className="text-sm text-amber-400">Choose two different funds to compare.</p>
        )}

        {overlapError && <p className="text-sm text-rose-400">{overlapError}</p>}

        {overlap && overlap.available && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-lg border border-neutral-800 p-4">
                <div className="text-xs uppercase tracking-wide text-neutral-500">Weighted Overlap</div>
                <div className="text-lg font-semibold mt-1">{formatNumber(overlap.weighted_overlap_pct, 1)}%</div>
                <div className="text-xs text-neutral-500 mt-1">
                  {overlap.overlap_label ? OVERLAP_LABELS[overlap.overlap_label] ?? overlap.overlap_label : "—"}
                </div>
              </div>
              <div className="rounded-lg border border-neutral-800 p-4">
                <div className="text-xs uppercase tracking-wide text-neutral-500">Sector Overlap</div>
                <div className="text-lg font-semibold mt-1">{formatNumber(overlap.sector_overlap_pct, 1)}%</div>
              </div>
              <div className="rounded-lg border border-neutral-800 p-4">
                <div className="text-xs uppercase tracking-wide text-neutral-500">Common Holdings</div>
                <div className="text-lg font-semibold mt-1">{overlap.common_securities_count}</div>
                <div className="text-xs text-neutral-500 mt-1">
                  {overlap.only_in_a_count} only in A · {overlap.only_in_b_count} only in B
                </div>
              </div>
              <div className="rounded-lg border border-neutral-800 p-4">
                <div className="text-xs uppercase tracking-wide text-neutral-500">Return Correlation</div>
                <div className="text-lg font-semibold mt-1">
                  {overlap.return_correlation !== null ? formatNumber(overlap.return_correlation, 2) : "N/A"}
                </div>
              </div>
            </div>

            <p className="text-xs text-neutral-500">
              <Link href={`/research/${overlap.fund_a.id}`} className="text-cyan-400 hover:text-cyan-300">
                {overlap.fund_a.scheme_name}
              </Link>{" "}
              (holdings as of {formatDate(overlap.as_of_date_a)}) vs.{" "}
              <Link href={`/research/${overlap.fund_b.id}`} className="text-cyan-400 hover:text-cyan-300">
                {overlap.fund_b.scheme_name}
              </Link>{" "}
              (holdings as of {formatDate(overlap.as_of_date_b)})
            </p>

            {overlap.common_holdings.length > 0 && (
              <div>
                <h2 className="text-sm uppercase tracking-wide text-neutral-500 mb-3">Common Holdings</h2>
                <div className="overflow-x-auto rounded-lg border border-neutral-800">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-neutral-800 text-left text-xs uppercase tracking-wide text-neutral-500">
                        <th className="px-4 py-2 font-medium">Security</th>
                        <th className="px-4 py-2 font-medium text-right">Weight in A</th>
                        <th className="px-4 py-2 font-medium text-right">Weight in B</th>
                        <th className="px-4 py-2 font-medium text-right">Shared</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-900">
                      {overlap.common_holdings.map((h) => (
                        <tr key={h.security_name}>
                          <td className="px-4 py-2">{h.security_name}</td>
                          <td className="px-4 py-2 text-right text-neutral-400">{formatNumber(h.weight_a, 2)}%</td>
                          <td className="px-4 py-2 text-right text-neutral-400">{formatNumber(h.weight_b, 2)}%</td>
                          <td className="px-4 py-2 text-right font-medium">{formatNumber(h.min_weight, 2)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div>
              <h2 className="text-sm uppercase tracking-wide text-neutral-500 mb-3">Sector Overlap</h2>
              <div className="overflow-x-auto rounded-lg border border-neutral-800">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-neutral-800 text-left text-xs uppercase tracking-wide text-neutral-500">
                      <th className="px-4 py-2 font-medium">Sector</th>
                      <th className="px-4 py-2 font-medium text-right">Weight in A</th>
                      <th className="px-4 py-2 font-medium text-right">Weight in B</th>
                      <th className="px-4 py-2 font-medium text-right">Shared</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-900">
                    {overlap.sector_detail.map((s) => (
                      <tr key={s.sector}>
                        <td className="px-4 py-2">{s.sector.replace(/^Sample: /, "")}</td>
                        <td className="px-4 py-2 text-right text-neutral-400">{formatNumber(s.weight_a, 2)}%</td>
                        <td className="px-4 py-2 text-right text-neutral-400">{formatNumber(s.weight_b, 2)}%</td>
                        <td className="px-4 py-2 text-right font-medium">{formatNumber(s.min_weight, 2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <p className="text-xs text-neutral-600 border-t border-neutral-900 pt-4">{overlap.disclaimer}</p>
          </div>
        )}

        {overlap && !overlap.available && (
          <p className="text-sm text-neutral-500">
            {overlap.reason === "no_holdings_data"
              ? "One or both funds have no disclosed portfolio holdings yet."
              : "Overlap data is not available for this pair."}
          </p>
        )}

        {!canCompare && !overlapError && (
          <p className="text-sm text-neutral-500">Pick two funds above to see how much they overlap.</p>
        )}
      </main>
    </div>
  );
}
