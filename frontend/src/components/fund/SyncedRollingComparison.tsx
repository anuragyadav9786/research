"use client";

import { useState } from "react";

import { formatPct } from "@/lib/format";
import type { RollingReturnDistribution } from "@/types/fund";

interface FundBarInput {
  label: string;
  distribution: RollingReturnDistribution;
}

/** Two rolling-return distribution bars, one per fund, on one shared
 * scale (same axis-sharing idea DistributionBar already supports via its
 * own scaleMin/scaleMax props) — plus a hover crosshair synced between
 * them: move the mouse over either bar and the same value position lights
 * up on both, so "where did Fund A's outcomes diverge from Fund B's at
 * this point in the range" is a glance, not a mental subtraction. Kept
 * separate from DistributionBar (used elsewhere as a plain, non-
 * interactive server-rendered bar) rather than bolting hover state onto
 * it, so this page's needs can't regress that component's other callers. */
export function SyncedRollingComparison({ fundA, fundB }: { fundA: FundBarInput; fundB: FundBarInput }) {
  const [hoverValue, setHoverValue] = useState<number | null>(null);

  const mins = [fundA.distribution.min, fundB.distribution.min].filter((v): v is number => v !== null);
  const maxs = [fundA.distribution.max, fundB.distribution.max].filter((v): v is number => v !== null);

  if (mins.length === 0 || maxs.length === 0) {
    return <p className="text-sm text-slate-500">Not enough rolling-return history for both funds to compare.</p>;
  }

  const scaleMin = Math.min(...mins);
  const scaleMax = Math.max(...maxs);

  return (
    <div className="space-y-3" onMouseLeave={() => setHoverValue(null)}>
      <ComparisonBar
        label={fundA.label}
        distribution={fundA.distribution}
        scaleMin={scaleMin}
        scaleMax={scaleMax}
        hoverValue={hoverValue}
        onHover={setHoverValue}
      />
      <ComparisonBar
        label={fundB.label}
        distribution={fundB.distribution}
        scaleMin={scaleMin}
        scaleMax={scaleMax}
        hoverValue={hoverValue}
        onHover={setHoverValue}
      />
      <p className="text-[11px] text-slate-500">
        Hover either bar to compare the same point on both, on a shared scale ({formatPct(scaleMin, 1)} to{" "}
        {formatPct(scaleMax, 1)}).{hoverValue !== null && <> Hovering: {formatPct(hoverValue, 2)}.</>}
      </p>
    </div>
  );
}

function ComparisonBar({
  label,
  distribution,
  scaleMin,
  scaleMax,
  hoverValue,
  onHover,
}: {
  label: string;
  distribution: RollingReturnDistribution;
  scaleMin: number;
  scaleMax: number;
  hoverValue: number | null;
  onHover: (v: number | null) => void;
}) {
  const { min, max, p10, p25, median, p75, p90 } = distribution;

  if (min === null || max === null) {
    return (
      <div>
        <p className="text-xs text-slate-400 mb-1">{label}</p>
        <p className="text-sm text-slate-500">Not enough history to show a distribution.</p>
      </div>
    );
  }

  const toPct = (v: number) => ((v - scaleMin) / (scaleMax - scaleMin)) * 100;
  const showZeroLine = scaleMin < 0 && scaleMax > 0;

  function handleMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    onHover(scaleMin + fraction * (scaleMax - scaleMin));
  }

  return (
    <div>
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <div
        className="relative h-8 rounded bg-slate-900 border border-slate-800 overflow-hidden cursor-crosshair"
        onMouseMove={handleMove}
      >
        {[25, 50, 75].map((pct) => (
          <div key={pct} className="absolute top-0 bottom-0 w-px bg-slate-700/40" style={{ left: `${pct}%` }} />
        ))}
        <div
          className="absolute top-0 bottom-0 bg-slate-700/50"
          style={{ left: `${toPct(p10 ?? min)}%`, right: `${100 - toPct(p90 ?? max)}%` }}
        />
        <div
          className="absolute top-0 bottom-0 bg-indigo-800/70"
          style={{ left: `${toPct(p25 ?? min)}%`, right: `${100 - toPct(p75 ?? max)}%` }}
        />
        {median !== null && (
          <div className="absolute top-0 bottom-0 w-0.5 bg-indigo-300" style={{ left: `${toPct(median)}%` }} />
        )}
        {showZeroLine && <div className="absolute top-0 bottom-0 w-px bg-slate-400" style={{ left: `${toPct(0)}%` }} />}
        {hoverValue !== null && hoverValue >= scaleMin && hoverValue <= scaleMax && (
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-amber-400 pointer-events-none"
            style={{ left: `${toPct(hoverValue)}%` }}
          />
        )}
      </div>
      <div className="flex justify-between text-xs text-slate-400 mt-1">
        <span>worst {formatPct(min)}</span>
        <span className="text-slate-300">median {formatPct(median)}</span>
        <span>best {formatPct(max)}</span>
      </div>
    </div>
  );
}
