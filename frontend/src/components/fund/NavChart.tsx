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
    return <p className="text-sm text-neutral-500">No NAV history available yet.</p>;
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
            <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
            <XAxis dataKey="date" tick={{ fill: "#a3a3a3", fontSize: 11 }} minTickGap={50} />
            <YAxis tick={{ fill: "#a3a3a3", fontSize: 11 }} width={44} />
            <Tooltip
              contentStyle={{ background: "#171717", border: "1px solid #404040", fontSize: 12 }}
              labelStyle={{ color: "#e5e5e5" }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="fund" name={fundLabel} stroke="#22d3ee" dot={false} strokeWidth={1.5} />
            {benchmarkLabel && (
              <Line
                type="monotone"
                dataKey="benchmark"
                name={benchmarkLabel}
                stroke="#a3a3a3"
                dot={false}
                strokeWidth={1.5}
                strokeDasharray="4 3"
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-neutral-500 mt-2">
        Rebased to 100 at the start of the available history for comparison — not actual investment amounts.
      </p>
    </div>
  );
}
