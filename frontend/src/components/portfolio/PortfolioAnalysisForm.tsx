"use client";

import { useState } from "react";
import Link from "next/link";

import { analysePortfolio, ApiError } from "@/lib/api";
import { formatDate, formatLakh, formatNumber, formatPct } from "@/lib/format";
import { AllocationBar } from "@/components/fund/AllocationBar";
import { Disclosure } from "@/components/fund/Disclosure";
import { StatCard } from "@/components/fund/StatCard";
import { CasUploadPanel } from "@/components/portfolio/CasUploadPanel";
import type { FundSummary } from "@/types/fund";
import type { PairwiseOverlapItem, PortfolioAnalysisResponse } from "@/types/portfolioAnalysis";

const MIN_ROWS = 2;
const MAX_ROWS = 10;

const HHI_LABELS: Record<string, string> = {
  diversified: "Diversified",
  moderate_concentration: "Moderate Concentration",
  high_concentration: "High Concentration",
};
const OVERLAP_LABELS: Record<string, string> = {
  low_overlap: "Low",
  moderate_overlap: "Moderate",
  high_overlap: "High",
};

// A round, illustrative principal — same convention as the homepage's
// Myth vs. Reality rupee-terms translation (see formatLakh in
// lib/format.ts) — for turning the portfolio's percentage drawdown into a
// concrete number, not a claim about any real investor's holding.
const ILLUSTRATIVE_PORTFOLIO_PRINCIPAL = 1_000_000;

function overlapInterpretation(overlapLabel: string): string {
  switch (overlapLabel) {
    case "high_overlap":
      return "These two funds share a significant portion of their underlying holdings — a decline in those shared companies would affect both funds at once, not just one.";
    case "moderate_overlap":
      return "These two funds share a moderate portion of their underlying holdings.";
    default:
      return "These two funds have relatively distinct underlying holdings.";
  }
}

/** Every fund name that appears in at least one high_overlap pair — the
 * plain-English version of "you hold N funds, but M of them have
 * significant overlapping exposure," Section 9's own worked example. */
function fundsWithHighOverlap(pairs: PairwiseOverlapItem[]): Set<number> {
  const ids = new Set<number>();
  for (const pair of pairs) {
    if (pair.overlap_label === "high_overlap") {
      ids.add(pair.fund_a_id);
      ids.add(pair.fund_b_id);
    }
  }
  return ids;
}

interface Row {
  fundId: string;
  weightPct: string;
}

function makeDefaultRows(funds: FundSummary[]): Row[] {
  return [
    { fundId: funds[0] ? String(funds[0].id) : "", weightPct: "60" },
    { fundId: funds[1] ? String(funds[1].id) : "", weightPct: "40" },
  ];
}

export function PortfolioAnalysisForm({ funds }: { funds: FundSummary[] }) {
  const [rows, setRows] = useState<Row[]>(() => makeDefaultRows(funds));
  const [result, setResult] = useState<PortfolioAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const totalWeight = rows.reduce((sum, r) => sum + (Number(r.weightPct) || 0), 0);

  function updateRow(index: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function addRow() {
    if (rows.length >= MAX_ROWS) return;
    const usedIds = new Set(rows.map((r) => r.fundId));
    const nextFund = funds.find((f) => !usedIds.has(String(f.id)));
    setRows((prev) => [...prev, { fundId: nextFund ? String(nextFund.id) : "", weightPct: "" }]);
  }

  function removeRow(index: number) {
    if (rows.length <= MIN_ROWS) return;
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const fundIds = rows.map((r) => r.fundId);
    if (fundIds.some((id) => !id)) {
      setError("Select a fund for every row.");
      return;
    }
    if (new Set(fundIds).size !== fundIds.length) {
      setError("Each fund can only appear once in the portfolio.");
      return;
    }
    if (Math.abs(totalWeight - 100) > 0.5) {
      setError(`Weights must sum to 100% (currently ${totalWeight.toFixed(1)}%).`);
      return;
    }

    setLoading(true);
    try {
      const holdings = rows.map((r) => ({ fund_id: Number(r.fundId), weight_pct: Number(r.weightPct) }));
      const data = await analysePortfolio(holdings);
      setResult(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not analyse this portfolio.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <CasUploadPanel maxRows={MAX_ROWS} onUseHoldings={(newRows) => setRows(newRows)} />

      <form onSubmit={handleSubmit} className="space-y-3">
        {rows.map((row, i) => (
          <div key={i} className="flex flex-wrap items-center gap-3">
            <select
              value={row.fundId}
              onChange={(e) => updateRow(i, { fundId: e.target.value })}
              className="min-w-[240px] rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm"
            >
              <option value="" disabled>Select a fund…</option>
              {funds.map((f) => (
                <option key={f.id} value={f.id}>{f.scheme_name}</option>
              ))}
            </select>
            <div className="flex items-center gap-1.5">
              <input
                type="number"
                min={0}
                max={100}
                step={0.1}
                value={row.weightPct}
                onChange={(e) => updateRow(i, { weightPct: e.target.value })}
                className="w-24 rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm"
              />
              <span className="text-sm text-slate-500">%</span>
            </div>
            <button
              type="button"
              onClick={() => removeRow(i)}
              disabled={rows.length <= MIN_ROWS}
              className="text-sm text-slate-500 hover:text-rose-400 disabled:opacity-30 disabled:hover:text-slate-500"
            >
              Remove
            </button>
          </div>
        ))}

        <div className="flex flex-wrap items-center gap-3 pt-1">
          <button
            type="button"
            onClick={addRow}
            disabled={rows.length >= MAX_ROWS}
            className="text-sm rounded-md border border-slate-800 px-3 py-1.5 text-slate-400 hover:text-slate-100 disabled:opacity-30"
          >
            + Add fund
          </button>
          <span className={`text-sm ${Math.abs(totalWeight - 100) > 0.5 ? "text-amber-400" : "text-slate-500"}`}>
            Total: {totalWeight.toFixed(1)}%
          </span>
          <button
            type="submit"
            disabled={loading}
            className="ml-auto rounded-md border border-slate-700 bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700 disabled:opacity-50"
          >
            {loading ? "Analysing…" : "Analyse Portfolio"}
          </button>
        </div>
      </form>

      {error && <p className="text-sm text-rose-400">{error}</p>}

      {result && (
        <div className="space-y-6 border-t border-slate-900 pt-6">
          <div>
            <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Portfolio</h2>
            <ul className="text-sm text-slate-300 space-y-1">
              {result.funds.map((f) => (
                <li key={f.fund_id} className="flex justify-between max-w-md">
                  <Link href={`/research/${f.fund_id}`} className="text-indigo-500 hover:text-indigo-600">
                    {f.scheme_name}
                  </Link>
                  <span>{formatNumber(f.weight_pct, 1)}%</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard
              label="Concentration (HHI)"
              value={result.concentration ? formatNumber(result.concentration.hhi, 0) : "—"}
              hint={result.concentration ? HHI_LABELS[result.concentration.hhi_label] : undefined}
              valueClassName={
                result.concentration?.hhi_label === "high_concentration"
                  ? "text-rose-400"
                  : result.concentration?.hhi_label === "moderate_concentration"
                    ? "text-amber-400"
                    : "text-emerald-400"
              }
            />
            <StatCard
              label="Volatility"
              value={result.risk.available ? `${formatNumber(result.risk.volatility_pct, 1)}%` : "N/A"}
              hint={result.risk.available ? undefined : "Insufficient return data"}
            />
            <StatCard
              label="Max Drawdown"
              value={result.drawdown.available ? formatPct(result.drawdown.max_drawdown_pct) : "N/A"}
              valueClassName="text-rose-400"
            />
            <StatCard
              label="Avg. Pairwise Correlation"
              value={result.average_pairwise_correlation !== null ? formatNumber(result.average_pairwise_correlation, 2) : "N/A"}
            />
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div className="rounded-lg border border-slate-800 p-4">
              <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Sector Allocation (Look-Through)</h3>
              <AllocationBar slices={result.sector_allocation} />
            </div>
            <div className="rounded-lg border border-slate-800 p-4">
              <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Market-Cap Allocation (Look-Through)</h3>
              <AllocationBar slices={result.market_cap_allocation} />
            </div>
          </div>

          {result.combined_top_holdings.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Combined Top Holdings</h3>
              <div className="overflow-x-auto rounded-lg border border-slate-800">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-4 py-2 font-medium">#</th>
                      <th className="px-4 py-2 font-medium">Security</th>
                      <th className="px-4 py-2 font-medium text-right">Effective Weight</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {result.combined_top_holdings.map((h) => (
                      <tr key={h.rank}>
                        <td className="px-4 py-2 text-slate-500">{h.rank}</td>
                        <td className="px-4 py-2">{h.security_name}</td>
                        <td className="px-4 py-2 text-right font-medium">{formatNumber(h.effective_weight_pct, 2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {result.pairwise_overlap.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Fund Overlap</h3>

              {(() => {
                const highOverlapIds = fundsWithHighOverlap(result.pairwise_overlap);
                return (
                  highOverlapIds.size > 0 && (
                    <p className="text-sm text-slate-200 mb-3">
                      You hold {result.funds.length} funds, but {highOverlapIds.size} of them have significant
                      overlapping exposure with at least one other fund in this portfolio.
                    </p>
                  )
                );
              })()}

              <ul className="space-y-2 mb-4">
                {result.pairwise_overlap.map((o) => (
                  <li key={`${o.fund_a_id}-${o.fund_b_id}`} className="text-sm text-slate-300">
                    <Link href={`/research/${o.fund_a_id}`} className="text-indigo-400 hover:text-indigo-300">
                      {o.fund_a_name}
                    </Link>{" "}
                    ↔{" "}
                    <Link href={`/research/${o.fund_b_id}`} className="text-indigo-400 hover:text-indigo-300">
                      {o.fund_b_name}
                    </Link>
                    : <span className="font-mono tabular-nums font-medium">{formatNumber(o.weighted_overlap_pct, 1)}%</span>{" "}
                    overlap ({OVERLAP_LABELS[o.overlap_label] ?? o.overlap_label}). {overlapInterpretation(o.overlap_label)}
                  </li>
                ))}
              </ul>

              <div className="overflow-x-auto rounded-lg border border-slate-800">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-4 py-2 font-medium">Fund A</th>
                      <th className="px-4 py-2 font-medium">Fund B</th>
                      <th className="px-4 py-2 font-medium text-right">Weighted Overlap</th>
                      <th className="px-4 py-2 font-medium text-right">Level</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {result.pairwise_overlap.map((o) => (
                      <tr key={`${o.fund_a_id}-${o.fund_b_id}`}>
                        <td className="px-4 py-2">{o.fund_a_name}</td>
                        <td className="px-4 py-2">{o.fund_b_name}</td>
                        <td className="px-4 py-2 text-right font-medium">{formatNumber(o.weighted_overlap_pct, 1)}%</td>
                        <td className="px-4 py-2 text-right text-slate-400">
                          {OVERLAP_LABELS[o.overlap_label] ?? o.overlap_label}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-3">
                <Disclosure label="What does this mean?">
                  <p className="text-sm text-slate-400">
                    Portfolio Overlap measures how much of two funds&rsquo; underlying holdings are the same
                    companies, weighted by position size in each fund. If several of your funds show high overlap
                    with each other, you&rsquo;re carrying less real diversification than the fund count alone
                    suggests — a downturn in those shared holdings affects several of your funds at once, not just
                    one.
                  </p>
                </Disclosure>
              </div>
            </div>
          )}

          {result.drawdown.available && result.drawdown.max_drawdown_pct !== null && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Blended Drawdown &amp; Recovery</h3>
              <p className="text-sm text-slate-300">
                On a hypothetical {formatLakh(ILLUSTRATIVE_PORTFOLIO_PRINCIPAL)} invested across this exact portfolio
                mix, the combined value would have fallen by{" "}
                <span className="font-mono tabular-nums font-semibold text-rose-400">
                  {formatPct(result.drawdown.max_drawdown_pct, 1)}
                </span>{" "}
                at the worst point — from {formatDate(result.drawdown.peak_date)} to{" "}
                {formatDate(result.drawdown.trough_date)} — to approximately{" "}
                <span className="font-mono tabular-nums font-semibold text-rose-400">
                  {formatLakh(ILLUSTRATIVE_PORTFOLIO_PRINCIPAL * (1 + result.drawdown.max_drawdown_pct / 100))}
                </span>
                .{" "}
                {result.drawdown.recovered && result.drawdown.recovery_duration_days != null
                  ? `It recovered to its prior peak by ${formatDate(result.drawdown.recovery_date)} — ${result.drawdown.recovery_duration_days} days after the trough.`
                  : "As of the latest available data, this blended portfolio has not yet recovered to its pre-drawdown peak."}
              </p>
              <p className="mt-2 text-[11px] text-slate-600">
                Illustrative only — assumes a lump-sum investment at this exact weight split, held from the
                portfolio&rsquo;s combined pre-drawdown peak. Not an actual investment outcome or recommendation.
              </p>
            </div>
          )}

          <p className="text-xs text-slate-600 border-t border-slate-900 pt-4">{result.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
