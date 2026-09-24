"use client";

import { useState } from "react";

import { analysePortfolio, ApiError } from "@/lib/api";
import { CasCompareTool } from "@/components/portfolio/CasCompareTool";
import { CasUploadPanel } from "@/components/portfolio/CasUploadPanel";
import { PortfolioAnalysisResult } from "@/components/portfolio/PortfolioAnalysisResult";
import type { FundSummary } from "@/types/fund";
import type { PortfolioAnalysisResponse } from "@/types/portfolioAnalysis";

const MIN_ROWS = 2;
const MAX_ROWS = 10;

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

      <CasCompareTool />

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
        <div className="border-t border-slate-900 pt-6">
          <PortfolioAnalysisResult result={result} />
        </div>
      )}
    </div>
  );
}
