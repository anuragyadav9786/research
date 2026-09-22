"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatDate, formatNav } from "@/lib/format";
import type { NavPoint } from "@/types/fund";

const MAX_CHART_POINTS = 300;

interface RebasedPoint {
  date: string;
  fund?: number;
  fundNav?: number;
  benchmark?: number;
  benchmarkIndex?: number;
}

function rebaseTo100(points: NavPoint[]): Map<string, { rebased: number; raw: number }> {
  const map = new Map<string, { rebased: number; raw: number }>();
  if (points.length === 0) return map;
  const base = points[0].value;
  for (const p of points) {
    map.set(p.date, { rebased: Number(((p.value / base) * 100).toFixed(2)), raw: p.value });
  }
  return map;
}

/** Custom tooltip, styled entirely with inline styles rather than Recharts'
 * contentStyle/labelStyle (which only cover the default label wrapper and
 * render illegibly on this dark theme — see RollingReturnBarChart.tsx's
 * equivalent fix). Shows only the real underlying figure (the fund's
 * actual NAV in rupees; the benchmark's actual index level) — the chart
 * itself stays rebased-to-100 so the two lines are visually comparable
 * despite their very different scales (a per-unit NAV vs. an index level
 * in the thousands), but the rebased number itself isn't a meaningful
 * standalone figure to read out on hover, so it isn't repeated here. */
function NavChartTooltip({
  active,
  payload,
  fundLabel,
  benchmarkLabel,
}: {
  active?: boolean;
  payload?: { payload: RebasedPoint }[];
  fundLabel: string;
  benchmarkLabel: string | null;
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
      <div style={{ color: "#e2e8f0", fontWeight: 600, marginBottom: 6, whiteSpace: "nowrap" }}>
        {formatDate(point.date)}
      </div>
      {point.fundNav !== undefined && (
        <div style={{ color: "#818cf8" }}>
          {fundLabel}: {formatNav(point.fundNav)}
        </div>
      )}
      {benchmarkLabel && point.benchmarkIndex !== undefined && (
        <div style={{ color: "#94a3b8" }}>
          {benchmarkLabel}: {point.benchmarkIndex.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
        </div>
      )}
    </div>
  );
}

export function NavChart({
  fundPoints,
  benchmarkPoints,
  fundLabel,
  benchmarkLabel,
}: {
  fundPoints: NavPoint[];
  benchmarkPoints: NavPoint[];
  fundLabel: string;
  benchmarkLabel: string | null;
}) {
  const fundRebased = rebaseTo100(fundPoints);
  const benchmarkRebased = rebaseTo100(benchmarkPoints);
  const allDates = Array.from(new Set([...fundRebased.keys(), ...benchmarkRebased.keys()])).sort();

  if (allDates.length === 0) {
    return <p className="text-sm text-slate-500">No NAV history available yet.</p>;
  }

  const step = Math.max(1, Math.floor(allDates.length / MAX_CHART_POINTS));
  const data: RebasedPoint[] = allDates
    .filter((_, i) => i % step === 0)
    .map((date) => {
      const fund = fundRebased.get(date);
      const benchmark = benchmarkRebased.get(date);
      return {
        date,
        fund: fund?.rebased,
        fundNav: fund?.raw,
        benchmark: benchmark?.rebased,
        benchmarkIndex: benchmark?.raw,
      };
    });

  return (
    <div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} minTickGap={50} />
            <YAxis
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              width={44}
              domain={[(min: number) => Math.floor(min * 0.97), (max: number) => Math.ceil(max * 1.03)]}
            />
            <Tooltip content={<NavChartTooltip fundLabel={fundLabel} benchmarkLabel={benchmarkLabel} />} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="fund" name={fundLabel} stroke="#818cf8" dot={false} strokeWidth={1.5} />
            {benchmarkLabel && (
              <Line
                type="monotone"
                dataKey="benchmark"
                name={benchmarkLabel}
                stroke="#94a3b8"
                dot={false}
                strokeWidth={1.5}
                strokeDasharray="4 3"
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-slate-500 mt-2">
        Rebased to 100 at the start of the available history for comparison — not actual investment amounts. The
        y-axis is zoomed to the actual range of the two lines rather than starting at zero, to make their relative
        movement easier to read. Hover a point to see the actual NAV / index level on that date.
      </p>
    </div>
  );
}
