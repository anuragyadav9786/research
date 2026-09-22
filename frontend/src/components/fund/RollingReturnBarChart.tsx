"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ApiError, getFundRollingReturnSeries } from "@/lib/api";
import { formatDate, formatPct } from "@/lib/format";
import type {
  Option,
  Plan,
  RollingReturnPoint,
  RollingReturnSeriesResponse,
  RollingSeriesLookback,
  RollingSeriesWindow,
} from "@/types/fund";

const WINDOW_OPTIONS: { value: RollingSeriesWindow; label: string }[] = [
  { value: "1m", label: "1 Month" },
  { value: "3m", label: "3 Month" },
  { value: "6m", label: "6 Month" },
  { value: "1y", label: "1 Year" },
];

const LOOKBACK_OPTIONS: { value: RollingSeriesLookback; label: string }[] = [
  { value: "1y", label: "1 Year" },
  { value: "3y", label: "3 Year" },
  { value: "5y", label: "5 Year" },
  { value: "10y", label: "10 Year" },
];

/** Custom tooltip content, styled entirely with inline styles rather than
 * Recharts' contentStyle/labelStyle props — those only style the default
 * label/item wrapper, which on a dark theme rendered illegible (dark text
 * with no explicit background behind it). Shows the bar's actual holding
 * period (start → end), not just the single date it happened to be keyed
 * by, so its significance is clear at a glance rather than requiring the
 * reader to infer it from the "Rolling window" selector above. */
function RollingReturnTooltip({
  active,
  payload,
  annualized,
}: {
  active?: boolean;
  payload?: { payload: RollingReturnPoint }[];
  annualized: boolean;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;
  return (
    <div
      style={{
        background: "#0f172a",
        border: "1px solid #334155",
        borderRadius: 6,
        padding: "8px 10px",
        fontSize: 12,
      }}
    >
      <div style={{ color: "#e2e8f0", fontWeight: 600, marginBottom: 4, whiteSpace: "nowrap" }}>
        {formatDate(point.start_date)} → {formatDate(point.end_date)}
      </div>
      <div style={{ color: point.return_pct >= 0 ? "#34d399" : "#fb7185" }}>
        {formatPct(point.return_pct)}
        <span style={{ color: "#94a3b8" }}>{annualized ? " (annualized)" : " (point-to-point)"}</span>
      </div>
    </div>
  );
}

export function RollingReturnBarChart({ fundId, plan, option }: { fundId: number; plan: Plan; option: Option }) {
  const [window, setWindow] = useState<RollingSeriesWindow>("3m");
  const [lookback, setLookback] = useState<RollingSeriesLookback>("1y");
  const [data, setData] = useState<RollingReturnSeriesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getFundRollingReturnSeries(fundId, { plan, option, window, lookback })
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load rolling returns.");
      });
    return () => {
      cancelled = true;
    };
  }, [fundId, plan, option, window, lookback]);

  const selectClass =
    "rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-slate-600";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
        <label className="flex items-center gap-2">
          Rolling window
          <select
            value={window}
            onChange={(e) => setWindow(e.target.value as RollingSeriesWindow)}
            className={selectClass}
          >
            {WINDOW_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Show last
          <select
            value={lookback}
            onChange={(e) => setLookback(e.target.value as RollingSeriesLookback)}
            className={selectClass}
          >
            {LOOKBACK_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="text-sm text-rose-400">{error}</p>}

      {!error && data && !data.available && (
        <p className="text-sm text-slate-500">
          Not enough NAV history for a {WINDOW_OPTIONS.find((o) => o.value === window)?.label.toLowerCase()} rolling
          window yet.
        </p>
      )}

      {!error && data?.available && (
        <>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="end_date" tick={{ fill: "#94a3b8", fontSize: 11 }} minTickGap={40} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} width={44} unit="%" />
                <Tooltip
                  cursor={{ fill: "rgba(148, 163, 184, 0.08)" }}
                  content={<RollingReturnTooltip annualized={data.annualized} />}
                />
                <Bar dataKey="return_pct">
                  {data.points.map((p, i) => (
                    <Cell key={i} fill={p.return_pct >= 0 ? "#34d399" : "#fb7185"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-slate-500">
            {data.annualized
              ? "Each bar is the annualized (CAGR) return over the holding period it covers — hover a bar to see its exact start and end date."
              : "Each bar is the point-to-point return over the holding period it covers (not annualized — the window is under a year) — hover a bar to see its exact start and end date."}
          </p>
        </>
      )}
    </div>
  );
}
