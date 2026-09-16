"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { NavPoint } from "@/types/fund";

const MAX_CHART_POINTS = 300;

function rebaseTo100(points: NavPoint[]): Map<string, number> {
  const map = new Map<string, number>();
  if (points.length === 0) return map;
  const base = points[0].value;
  for (const p of points) {
    map.set(p.date, Number(((p.value / base) * 100).toFixed(2)));
  }
  return map;
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
  const data = allDates
    .filter((_, i) => i % step === 0)
    .map((date) => ({ date, fund: fundRebased.get(date), benchmark: benchmarkRebased.get(date) }));

  return (
    <div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} minTickGap={50} />
            <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} width={44} />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 12 }}
              labelStyle={{ color: "#e2e8f0" }}
            />
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
        Rebased to 100 at the start of the available history for comparison — not actual investment amounts.
      </p>
    </div>
  );
}
