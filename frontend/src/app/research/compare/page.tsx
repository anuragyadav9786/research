import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { Disclosure } from "@/components/fund/Disclosure";
import { SyncedRollingComparison } from "@/components/fund/SyncedRollingComparison";
import { ApiError, getFundIntelligence, getFundOverlap, listAllFunds } from "@/lib/api";
import { formatDate, formatNumber, formatPct } from "@/lib/format";
import type { IntelligenceResponse } from "@/types/fund";

const OVERLAP_LABELS: Record<string, string> = {
  low_overlap: "Low Overlap",
  moderate_overlap: "Moderate Overlap",
  high_overlap: "High Overlap",
};

const CAGR_WINDOWS = ["1y", "3y", "5y"] as const;
const CAGR_WINDOW_LABELS: Record<string, string> = { "1y": "1Y CAGR", "3y": "3Y CAGR", "5y": "5Y CAGR" };

/** A small pill shown only in the winning side's own cell — the brief's
 * "delta tag for downside defense" — used only on the two rows where
 * "defends better" has an unambiguous real-data meaning (smaller-
 * magnitude drawdown, lower downside capture). Other rows (CAGR, Sharpe)
 * just bold+color the higher number; "better" there is closer to opinion
 * than a tag should claim. */
function DefenseTag() {
  return (
    <span className="ml-2 inline-flex items-center rounded-full bg-emerald-900/60 text-emerald-300 text-[10px] px-2 py-0.5 whitespace-nowrap">
      Defends better
    </span>
  );
}

function HeadToHeadRow({
  label,
  valueA,
  valueB,
  formatValue,
  leader,
  defenseWinner,
}: {
  label: string;
  valueA: number | null;
  valueB: number | null;
  formatValue: (v: number) => string;
  /** Which side to color as ahead on this row — independent of
   * `defenseWinner` since not every row is about downside defense. */
  leader: "a" | "b" | "tie" | null;
  /** Present only on the two downside-defense rows; the side named here
   * (never both) gets the DefenseTag in its own cell. */
  defenseWinner?: "a" | "b" | "tie" | null;
}) {
  const showTag = valueA !== null && valueB !== null;
  return (
    <tr className="border-b border-slate-900">
      <td className="px-4 py-3 text-sm text-slate-400">{label}</td>
      <td className={`px-4 py-3 text-sm text-right font-mono tabular-nums ${leader === "a" ? "text-emerald-400 font-semibold" : "text-slate-200"}`}>
        {valueA !== null ? formatValue(valueA) : "N/A"}
        {showTag && defenseWinner === "a" && <DefenseTag />}
      </td>
      <td className={`px-4 py-3 text-sm text-right font-mono tabular-nums ${leader === "b" ? "text-emerald-400 font-semibold" : "text-slate-200"}`}>
        {valueB !== null ? formatValue(valueB) : "N/A"}
        {showTag && defenseWinner === "b" && <DefenseTag />}
      </td>
    </tr>
  );
}

/** Real per-fund figures compared side by side — the platform's own
 * "Head-to-Head Benchmark" homepage promise, previously unfulfilled here
 * (this page only ever showed portfolio-overlap data, never returns or
 * risk). Sticky column header (top-16, matching SiteHeader's own height)
 * so the two fund names stay visible while scrolling past a long row
 * list; the two downside rows carry a DefenseTag; the rolling-return
 * distributions get the synced-hover comparison bars. */
function HeadToHeadPerformance({
  intelligenceA,
  intelligenceB,
}: {
  intelligenceA: IntelligenceResponse;
  intelligenceB: IntelligenceResponse;
}) {
  const { fund: fundA, returns: returnsA, risk: riskA, drawdown: drawdownA, rolling_3y: rollingA } = intelligenceA;
  const { fund: fundB, returns: returnsB, risk: riskB, drawdown: drawdownB, rolling_3y: rollingB } = intelligenceB;

  function leaderFor(a: number | null, b: number | null): "a" | "b" | "tie" | null {
    if (a === null || b === null) return null;
    if (a === b) return "tie";
    return a > b ? "a" : "b";
  }

  // Smaller-magnitude drawdown, and lower downside capture, defend
  // better — both real, already-computed figures (drawdown.max_drawdown_pct,
  // risk.downside_capture_pct), not a derived/estimated score.
  const drawdownDefense = (() => {
    const a = drawdownA.available ? drawdownA.max_drawdown_pct : null;
    const b = drawdownB.available ? drawdownB.max_drawdown_pct : null;
    if (a === null || b === null) return null;
    if (a === b) return "tie" as const;
    return a > b ? ("a" as const) : ("b" as const);
  })();
  const captureDefense = (() => {
    const a = riskA.available ? riskA.downside_capture_pct : null;
    const b = riskB.available ? riskB.downside_capture_pct : null;
    if (a === null || b === null) return null;
    if (a === b) return "tie" as const;
    return a < b ? ("a" as const) : ("b" as const);
  })();

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-800">
        <table className="w-full">
          <thead>
            <tr className="sticky top-16 z-10 bg-slate-950/95 backdrop-blur border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3 font-medium">Head-to-Head Performance</th>
              <th className="px-4 py-3 font-medium text-right">
                <Link href={`/research/${fundA.id}`} className="text-indigo-400 hover:text-indigo-300">
                  {fundA.scheme_name}
                </Link>
              </th>
              <th className="px-4 py-3 font-medium text-right">
                <Link href={`/research/${fundB.id}`} className="text-indigo-400 hover:text-indigo-300">
                  {fundB.scheme_name}
                </Link>
              </th>
            </tr>
          </thead>
          <tbody>
            {CAGR_WINDOWS.map((w) => {
              const a = returnsA.windows[w]?.available ? returnsA.windows[w].cagr_pct : null;
              const b = returnsB.windows[w]?.available ? returnsB.windows[w].cagr_pct : null;
              return (
                <HeadToHeadRow
                  key={w}
                  label={CAGR_WINDOW_LABELS[w]}
                  valueA={a}
                  valueB={b}
                  formatValue={(v) => formatPct(v, 1)}
                  leader={leaderFor(a, b)}
                />
              );
            })}
            <HeadToHeadRow
              label="Max Drawdown"
              valueA={drawdownA.available ? drawdownA.max_drawdown_pct : null}
              valueB={drawdownB.available ? drawdownB.max_drawdown_pct : null}
              formatValue={(v) => formatPct(v, 1)}
              leader={drawdownDefense}
              defenseWinner={drawdownDefense}
            />
            <HeadToHeadRow
              label="Downside Capture"
              valueA={riskA.available ? riskA.downside_capture_pct : null}
              valueB={riskB.available ? riskB.downside_capture_pct : null}
              formatValue={(v) => `${formatNumber(v, 1)}%`}
              leader={captureDefense}
              defenseWinner={captureDefense}
            />
            <HeadToHeadRow
              label="Sharpe Ratio"
              valueA={riskA.available ? riskA.sharpe_ratio : null}
              valueB={riskB.available ? riskB.sharpe_ratio : null}
              formatValue={(v) => formatNumber(v)}
              leader={leaderFor(riskA.available ? riskA.sharpe_ratio : null, riskB.available ? riskB.sharpe_ratio : null)}
            />
          </tbody>
        </table>
      </div>

      {rollingA.available && rollingB.available && (
        <div className="rounded-lg border border-slate-800 p-4">
          <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">
            Rolling 3-Year Return Distribution
          </h2>
          <SyncedRollingComparison
            fundA={{ label: fundA.scheme_name, distribution: rollingA.distribution }}
            fundB={{ label: fundB.scheme_name, distribution: rollingB.distribution }}
          />
        </div>
      )}
    </div>
  );
}

export const metadata = { title: "Compare Funds — ThinkFin" };

export default async function CompareFundsPage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>;
}) {
  const { a, b } = await searchParams;
  const funds = await listAllFunds();

  const fundIdA = a ? Number(a) : undefined;
  const fundIdB = b ? Number(b) : undefined;
  const canCompare = fundIdA && fundIdB && fundIdA !== fundIdB;

  let overlapError: string | null = null;
  const overlapPromise = canCompare
    ? getFundOverlap(fundIdA, fundIdB).catch((err) => {
        overlapError = err instanceof ApiError ? err.message : "Could not load overlap data.";
        return null;
      })
    : Promise.resolve(null);

  // getFundIntelligence bundles returns/risk/rolling(3y)/drawdown into one
  // call per fund (same endpoint the fund detail page uses) — two calls
  // total for the head-to-head section below, not eight. A fund with no
  // direct/growth variant, or too little NAV history for a metric, still
  // renders: intelligenceA/B fall back to null and each metric row below
  // already handles a missing value as "N/A", same as everywhere else on
  // this platform.
  const [overlap, intelligenceA, intelligenceB] = await Promise.all([
    overlapPromise,
    canCompare ? getFundIntelligence(fundIdA).catch(() => null) : Promise.resolve(null),
    canCompare ? getFundIntelligence(fundIdB).catch(() => null) : Promise.resolve(null),
  ]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="compare" />

      <main className="px-8 py-10 max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Compare Funds</h1>
          <p className="text-slate-400 text-sm mt-1">
            Place two funds side by side — returns, risk, and how much they actually overlap in holdings and sectors.
          </p>
        </div>

        <form method="get" className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="block text-xs uppercase tracking-wide text-slate-500 mb-1">Fund A</span>
            <select
              name="a"
              defaultValue={a ?? ""}
              className="min-w-[220px] rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm"
            >
              <option value="" disabled>Select a fund…</option>
              {funds.map((f) => (
                <option key={f.id} value={f.id}>{f.scheme_name}</option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="block text-xs uppercase tracking-wide text-slate-500 mb-1">Fund B</span>
            <select
              name="b"
              defaultValue={b ?? ""}
              className="min-w-[220px] rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm"
            >
              <option value="" disabled>Select a fund…</option>
              {funds.map((f) => (
                <option key={f.id} value={f.id}>{f.scheme_name}</option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="rounded-md border border-slate-700 bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700"
          >
            Compare
          </button>
        </form>

        {fundIdA && fundIdB && fundIdA === fundIdB && (
          <p className="text-sm text-amber-400">Choose two different funds to compare.</p>
        )}

        {overlapError && <p className="text-sm text-rose-400">{overlapError}</p>}

        {canCompare && intelligenceA && intelligenceB && (
          <HeadToHeadPerformance intelligenceA={intelligenceA} intelligenceB={intelligenceB} />
        )}

        {overlap && overlap.available && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-lg border border-slate-800 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Weighted Overlap</div>
                <div className="text-lg font-semibold mt-1">{formatNumber(overlap.weighted_overlap_pct, 1)}%</div>
                <div className="text-xs text-slate-500 mt-1">
                  {overlap.overlap_label ? OVERLAP_LABELS[overlap.overlap_label] ?? overlap.overlap_label : "—"}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Sector Overlap</div>
                <div className="text-lg font-semibold mt-1">{formatNumber(overlap.sector_overlap_pct, 1)}%</div>
              </div>
              <div className="rounded-lg border border-slate-800 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Common Holdings</div>
                <div className="text-lg font-semibold mt-1">{overlap.common_securities_count}</div>
                <div className="text-xs text-slate-500 mt-1">
                  {overlap.only_in_a_count} only in A · {overlap.only_in_b_count} only in B
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">Return Correlation</div>
                <div className="text-lg font-semibold mt-1">
                  {overlap.return_correlation !== null ? formatNumber(overlap.return_correlation, 2) : "N/A"}
                </div>
              </div>
            </div>

            <p className="text-sm text-slate-300">
              <Link href={`/research/${overlap.fund_a.id}`} className="text-indigo-400 hover:text-indigo-300">
                {overlap.fund_a.scheme_name}
              </Link>{" "}
              ↔{" "}
              <Link href={`/research/${overlap.fund_b.id}`} className="text-indigo-400 hover:text-indigo-300">
                {overlap.fund_b.scheme_name}
              </Link>
              : {formatNumber(overlap.weighted_overlap_pct, 1)}% overlap.{" "}
              {overlap.common_securities_count > 0
                ? `They share ${overlap.common_securities_count} underlying holding${overlap.common_securities_count === 1 ? "" : "s"}, weighted by how much of each fund's disclosed portfolio those holdings represent.`
                : "They share no disclosed holdings in common."}
            </p>

            <Disclosure label="What does this mean?">
              <p className="text-sm text-slate-400">
                Portfolio Overlap measures how much of two funds&rsquo; underlying holdings are the same companies,
                weighted by position size in each fund. High overlap means holding both funds gives you less real
                diversification than owning two different funds would suggest — you&rsquo;re more exposed to the
                same set of companies than the fund count implies.
              </p>
            </Disclosure>

            <p className="text-xs text-slate-500">
              <Link href={`/research/${overlap.fund_a.id}`} className="text-indigo-500 hover:text-indigo-600">
                {overlap.fund_a.scheme_name}
              </Link>{" "}
              (holdings as of {formatDate(overlap.as_of_date_a)}) vs.{" "}
              <Link href={`/research/${overlap.fund_b.id}`} className="text-indigo-500 hover:text-indigo-600">
                {overlap.fund_b.scheme_name}
              </Link>{" "}
              (holdings as of {formatDate(overlap.as_of_date_b)})
            </p>

            {overlap.common_holdings.length > 0 && (
              <div>
                <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Common Holdings</h2>
                <div className="overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                        <th className="px-4 py-2 font-medium">Security</th>
                        <th className="px-4 py-2 font-medium text-right">Weight in A</th>
                        <th className="px-4 py-2 font-medium text-right">Weight in B</th>
                        <th className="px-4 py-2 font-medium text-right">Shared</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {overlap.common_holdings.map((h) => (
                        <tr key={h.security_name}>
                          <td className="px-4 py-2">{h.security_name}</td>
                          <td className="px-4 py-2 text-right text-slate-400">{formatNumber(h.weight_a, 2)}%</td>
                          <td className="px-4 py-2 text-right text-slate-400">{formatNumber(h.weight_b, 2)}%</td>
                          <td className="px-4 py-2 text-right font-medium">{formatNumber(h.min_weight, 2)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div>
              <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Sector Overlap</h2>
              <div className="overflow-x-auto rounded-lg border border-slate-800">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-4 py-2 font-medium">Sector</th>
                      <th className="px-4 py-2 font-medium text-right">Weight in A</th>
                      <th className="px-4 py-2 font-medium text-right">Weight in B</th>
                      <th className="px-4 py-2 font-medium text-right">Shared</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {overlap.sector_detail.map((s) => (
                      <tr key={s.sector}>
                        <td className="px-4 py-2">{s.sector.replace(/^Sample: /, "")}</td>
                        <td className="px-4 py-2 text-right text-slate-400">{formatNumber(s.weight_a, 2)}%</td>
                        <td className="px-4 py-2 text-right text-slate-400">{formatNumber(s.weight_b, 2)}%</td>
                        <td className="px-4 py-2 text-right font-medium">{formatNumber(s.min_weight, 2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <p className="text-xs text-slate-600 border-t border-slate-900 pt-4">{overlap.disclaimer}</p>
          </div>
        )}

        {overlap && !overlap.available && (
          <p className="text-sm text-slate-500">
            {overlap.reason === "no_holdings_data"
              ? "One or both funds have no disclosed portfolio holdings yet."
              : "Overlap data is not available for this pair."}
          </p>
        )}

        {!canCompare && !overlapError && (
          <p className="text-sm text-slate-500">Pick two funds above to see how much they overlap.</p>
        )}
      </main>
    </div>
  );
}
