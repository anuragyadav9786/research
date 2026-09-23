"use client";

import { useState } from "react";

import { ApiError, parseCasStatement } from "@/lib/api";
import { formatDate, formatPct, formatRupees, signColorClass } from "@/lib/format";
import { Disclosure } from "@/components/fund/Disclosure";
import { StatCard } from "@/components/fund/StatCard";
import type { CASParseResponse } from "@/types/cas";

const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024;

const UNMATCHED_REASON_LABELS: Record<string, string> = {
  isin_not_found: "not in our fund database yet",
};

export function CasUploadPanel({
  maxRows,
  onUseHoldings,
}: {
  maxRows: number;
  onUseHoldings: (rows: { fundId: string; weightPct: string }[]) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CASParseResponse | null>(null);
  const [applied, setApplied] = useState(false);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setResult(null);
    setApplied(false);
    setError(null);
    if (selected && selected.size > MAX_FILE_SIZE_BYTES) {
      setError("File too large — maximum 5 MB.");
      setFile(null);
      return;
    }
    setFile(selected);
  }

  async function handleParse(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Choose a CAS PDF first.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    setApplied(false);
    try {
      const data = await parseCasStatement(file, password || undefined);
      setResult(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not parse this statement.");
    } finally {
      setLoading(false);
    }
  }

  function handleUseHoldings() {
    if (!result) return;
    const top = [...result.matched_holdings].sort((a, b) => b.market_value - a.market_value).slice(0, maxRows);
    const totalValue = top.reduce((sum, h) => sum + h.market_value, 0);
    const rows = top.map((h) => ({
      fundId: String(h.fund_id),
      weightPct: totalValue > 0 ? ((h.market_value / totalValue) * 100).toFixed(1) : "0",
    }));
    while (rows.length < 2) rows.push({ fundId: "", weightPct: "" });
    onUseHoldings(rows);
    setApplied(true);
  }

  const matchedCount = result?.matched_holdings.length ?? 0;
  const truncated = matchedCount > maxRows;

  return (
    <div className="rounded-lg border border-slate-800 p-4">
      <h2 className="text-sm font-medium text-slate-200">Upload CAS Statement (BETA)</h2>
      <p className="text-xs text-slate-500 mt-1">
        Upload your Consolidated Account Statement (CAMS/KFintech) to prefill your actual holdings below, instead of
        picking funds by hand. Values are read as of the statement&rsquo;s own generation date — not refreshed live.
      </p>

      <form onSubmit={handleParse} className="mt-3 space-y-3">
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-xs text-slate-500">
            Upload CAS (PDF)
            <input
              type="file"
              accept="application/pdf"
              onChange={handleFileChange}
              className="mt-1 block w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border file:border-slate-800 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:text-slate-300 file:hover:bg-slate-800"
            />
            <span className="text-[11px] text-slate-600">PDF only · Max 5 MB</span>
          </label>
          <label className="text-xs text-slate-500">
            Password (if protected)
            <div className="mt-1 flex items-center gap-2">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="PDF password"
                className="w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-slate-600"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="text-xs text-indigo-400 hover:text-indigo-300 whitespace-nowrap"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>
        </div>

        <button
          type="submit"
          disabled={loading || !file}
          className="rounded-md border border-slate-700 bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700 disabled:opacity-50"
        >
          {loading ? "Parsing…" : "Proceed to Parse"}
        </button>
      </form>

      {error && <p className="text-sm text-rose-400 mt-3">{error}</p>}

      {result && (
        <div className="mt-4 border-t border-slate-900 pt-3 space-y-3">
          <p className="text-sm text-slate-300">
            Found {matchedCount} holding{matchedCount === 1 ? "" : "s"} in our fund database
            {result.as_of_date && <> as of {formatDate(result.as_of_date)}</>}
            {matchedCount > 0 && <>, worth {formatRupees(result.matched_market_value)}</>}.
            {truncated && ` Only the ${maxRows} largest are used — analysis supports up to ${maxRows} funds.`}
          </p>

          {result.overview && result.overview.matched_scheme_count > 0 && (
            <div className="space-y-2">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard label="Total Invested" value={formatRupees(result.overview.total_invested)} />
                <StatCard label="Current Value" value={formatRupees(result.overview.total_current_value)} />
                <StatCard
                  label="Portfolio XIRR"
                  value={result.overview.portfolio_xirr_pct !== null ? formatPct(result.overview.portfolio_xirr_pct) : "N/A"}
                  valueClassName={
                    result.overview.portfolio_xirr_pct !== null
                      ? signColorClass(result.overview.portfolio_xirr_pct)
                      : "text-slate-600"
                  }
                  hint={
                    result.overview.portfolio_xirr_pct === null
                      ? "Not enough cash-flow history to solve for a rate"
                      : undefined
                  }
                />
                <StatCard
                  label="Total Gain"
                  value={formatRupees(result.overview.total_gain)}
                  valueClassName={signColorClass(result.overview.total_gain)}
                  hint={`Realized ${formatRupees(result.overview.total_realized_gain)} · Unrealized ${formatRupees(result.overview.total_unrealized_gain)}`}
                />
              </div>
              <Disclosure label="What is XIRR?">
                <p className="text-sm text-slate-400">
                  XIRR measures the annualized return earned on your actual investment cash flows, taking the timing
                  of each investment and withdrawal into account — a fairer measure than a simple point-to-point
                  return when money went in and out at different times (lump sums, SIP installments, redemptions).
                </p>
                <p className="text-sm text-slate-400 mt-2">
                  Computed from every Purchase/SIP (money you paid in) and Redemption (money you received) in this
                  statement, plus the current value of what&rsquo;s still held. Switches between funds already in
                  this portfolio aren&rsquo;t counted as new money in or out — internal transfers, not external cash
                  flow.
                </p>
              </Disclosure>
            </div>
          )}

          {matchedCount > 0 && (
            <ul className="text-sm text-slate-300 space-y-1">
              {result.matched_holdings.map((h) => (
                <li key={h.isin} className="flex justify-between max-w-md">
                  <span>{h.scheme_name}</span>
                  <span className="font-mono tabular-nums">{formatRupees(h.market_value)}</span>
                </li>
              ))}
            </ul>
          )}

          {result.unmatched_holdings.length > 0 && (
            <div>
              <p className="text-xs text-slate-500 mb-1">
                Excluded — not yet in our fund database, so left out of the analysis:
              </p>
              <ul className="text-xs text-slate-500 space-y-0.5">
                {result.unmatched_holdings.map((h) => (
                  <li key={h.isin}>
                    {h.scheme_name} ({h.isin}) — {formatRupees(h.market_value)} —{" "}
                    {UNMATCHED_REASON_LABELS[h.reason] ?? h.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {matchedCount > 0 ? (
            <button
              type="button"
              onClick={handleUseHoldings}
              className="rounded-md border border-indigo-700 bg-indigo-900/40 px-4 py-2 text-sm text-indigo-200 hover:bg-indigo-900/60"
            >
              {applied ? "Applied — using these holdings below" : `Use these ${Math.min(matchedCount, maxRows)} holdings`}
            </button>
          ) : (
            <p className="text-sm text-amber-400">
              None of the holdings in this statement are in our fund database yet — add funds manually below instead.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
