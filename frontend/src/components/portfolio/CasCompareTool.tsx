"use client";

import { useState } from "react";

import { ApiError, compareCasStatements } from "@/lib/api";
import { formatDate, formatPct, formatRupees, signColorClass } from "@/lib/format";
import { Disclosure } from "@/components/fund/Disclosure";
import { StatCard } from "@/components/fund/StatCard";
import type { CASComparisonResponse } from "@/types/cas";

const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024;

function ChangeStatCard({
  label,
  previous,
  current,
  change,
}: {
  label: string;
  previous: number;
  current: number;
  change: number;
}) {
  return (
    <StatCard
      label={label}
      value={formatRupees(current)}
      valueClassName={signColorClass(change)}
      hint={`${formatRupees(previous)} → ${formatRupees(current)} (${change >= 0 ? "+" : ""}${formatRupees(change)})`}
    />
  );
}

/** Portfolio Analysis §"what changed over time": upload two CAS
 * statements from different dates and see what changed between them.
 * Stateless — same as every other CAS feature, nothing here is persisted
 * or remembered between visits; both files are sent together in one
 * request. See backend/app/services/cas_comparison_service.py for the
 * exact pricing convention (both snapshots priced at today's latest NAV,
 * so the diff isolates what you did from market movement in between). */
export function CasCompareTool() {
  const [previousFile, setPreviousFile] = useState<File | null>(null);
  const [previousPassword, setPreviousPassword] = useState("");
  const [currentFile, setCurrentFile] = useState<File | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CASComparisonResponse | null>(null);

  function handleFile(setter: (f: File | null) => void, e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setResult(null);
    setError(null);
    if (selected && selected.size > MAX_FILE_SIZE_BYTES) {
      setError("File too large — maximum 5 MB.");
      setter(null);
      return;
    }
    setter(selected);
  }

  async function handleCompare(e: React.FormEvent) {
    e.preventDefault();
    if (!previousFile || !currentFile) {
      setError("Choose both statements first.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await compareCasStatements(
        previousFile,
        previousPassword || undefined,
        currentFile,
        currentPassword || undefined,
      );
      setResult(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not compare these statements.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-800 p-4">
      <h2 className="text-sm font-medium text-slate-200">Compare Two Statements</h2>
      <p className="text-xs text-slate-500 mt-1">
        Upload an earlier CAS and a more recent one to see what changed — new or exited holdings, value and weight
        movement per scheme, and asset-allocation drift. Both statements are compared in this one request; neither
        is saved.
      </p>

      <form onSubmit={handleCompare} className="mt-3 space-y-3">
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="rounded-md border border-slate-800 p-3">
            <label className="text-xs text-slate-500">
              Previous (earlier) Statement
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => handleFile(setPreviousFile, e)}
                className="mt-1 block w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border file:border-slate-800 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:text-slate-300 file:hover:bg-slate-800"
              />
            </label>
            <input
              type="password"
              value={previousPassword}
              onChange={(e) => setPreviousPassword(e.target.value)}
              placeholder="Password (if protected)"
              className="mt-2 w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-slate-600"
            />
          </div>
          <div className="rounded-md border border-slate-800 p-3">
            <label className="text-xs text-slate-500">
              Current (recent) Statement
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => handleFile(setCurrentFile, e)}
                className="mt-1 block w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border file:border-slate-800 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:text-slate-300 file:hover:bg-slate-800"
              />
            </label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Password (if protected)"
              className="mt-2 w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-slate-600"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || !previousFile || !currentFile}
          className="rounded-md border border-slate-700 bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700 disabled:opacity-50"
        >
          {loading ? "Comparing…" : "Compare"}
        </button>
      </form>

      {error && <p className="text-sm text-rose-400 mt-3">{error}</p>}

      {result && (
        <div className="mt-4 border-t border-slate-900 pt-3 space-y-4">
          <p className="text-sm text-slate-300">
            {formatDate(result.previous_as_of_date)} → {formatDate(result.current_as_of_date)}
            {result.span_days !== null && <> · {result.span_days} days apart</>}
            {result.dates_swapped && (
              <span className="block text-xs text-amber-400 mt-1">
                The two files were uploaded in reverse order — corrected automatically.
              </span>
            )}
          </p>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <ChangeStatCard
              label="Total Invested"
              previous={result.total_invested_previous}
              current={result.total_invested_current}
              change={result.total_invested_change}
            />
            <ChangeStatCard
              label="Current Value"
              previous={result.total_current_value_previous}
              current={result.total_current_value_current}
              change={result.total_current_value_change}
            />
            <ChangeStatCard
              label="Total Gain"
              previous={result.total_gain_previous}
              current={result.total_gain_current}
              change={result.total_gain_change}
            />
          </div>

          {(result.portfolio_xirr_pct_previous !== null || result.portfolio_xirr_pct_current !== null) && (
            <p className="text-sm text-slate-400">
              Portfolio XIRR:{" "}
              <span className="font-mono tabular-nums">
                {result.portfolio_xirr_pct_previous !== null ? formatPct(result.portfolio_xirr_pct_previous) : "N/A"}
              </span>{" "}
              →{" "}
              <span className="font-mono tabular-nums">
                {result.portfolio_xirr_pct_current !== null ? formatPct(result.portfolio_xirr_pct_current) : "N/A"}
              </span>
            </p>
          )}

          {result.new_schemes.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-1">New Holdings</h3>
              <ul className="text-sm text-slate-300 space-y-1">
                {result.new_schemes.map((s) => (
                  <li key={s.isin} className="flex justify-between max-w-md">
                    <span>{s.scheme_name}</span>
                    <span className="font-mono tabular-nums text-emerald-400">{formatRupees(s.current_value)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.exited_schemes.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-1">Exited Holdings</h3>
              <ul className="text-sm text-slate-300 space-y-1">
                {result.exited_schemes.map((s) => (
                  <li key={s.isin} className="flex justify-between max-w-md">
                    <span>{s.scheme_name}</span>
                    <span className="font-mono tabular-nums text-slate-500">
                      was {formatRupees(s.previous_value)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.scheme_changes.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Held in Both — What Changed</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-900">
                      <th className="py-1.5 pr-3 font-normal">Scheme</th>
                      <th className="py-1.5 px-3 font-normal text-right">Value Change</th>
                      <th className="py-1.5 pl-3 font-normal text-right">Weight Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.scheme_changes.map((s) => (
                      <tr key={s.isin} className="border-b border-slate-900/60 last:border-0">
                        <td className="py-1.5 pr-3 text-slate-300">{s.scheme_name}</td>
                        <td className={`py-1.5 px-3 text-right font-mono tabular-nums ${signColorClass(s.value_change)}`}>
                          {formatRupees(s.value_change)}
                        </td>
                        <td className="py-1.5 pl-3 text-right font-mono tabular-nums text-slate-400">
                          {s.weight_pct_change !== null ? formatPct(s.weight_pct_change, 1) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {result.asset_allocation_drift.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Asset Allocation Drift</h3>
              <ul className="text-sm text-slate-300 space-y-1">
                {result.asset_allocation_drift.map((d) => (
                  <li key={d.label} className="flex justify-between max-w-md">
                    <span>{d.label}</span>
                    <span className="font-mono tabular-nums">
                      {d.previous_weight_pct.toFixed(1)}% → {d.current_weight_pct.toFixed(1)}%{" "}
                      <span className={signColorClass(d.weight_pct_change)}>
                        ({formatPct(d.weight_pct_change, 1)})
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <Disclosure label="Why both snapshots use today's prices">
            <p className="text-sm text-slate-400">
              Both statements&rsquo; holdings are valued at our platform&rsquo;s latest known NAV, not at each
              statement&rsquo;s own generation date. That means every change shown here reflects what you actually
              did between the two statements — bought, sold, switched — not market movement in between. Portfolio
              XIRR (money-weighted return) is the figure for that.
            </p>
          </Disclosure>

          <p className="text-xs text-slate-600 border-t border-slate-900 pt-3">{result.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
