import { formatPct } from "@/lib/format";
import type { RollingReturnDistribution } from "@/types/fund";

/** A lightweight percentile-range visualization for rolling returns — no
 * charting library needed for a single-axis distribution like this. Shows
 * the p10-p90 band, the p25-p75 "typical" band, the median, and a 0%
 * reference line so it's immediately visible whether typical outcomes
 * were positive or negative. */
export function DistributionBar({
  distribution,
  scaleMin,
  scaleMax,
}: {
  distribution: RollingReturnDistribution;
  /** Override the axis range so multiple bars can share one scale — e.g.
   * comparing two funds side by side, where each bar's own min/max would
   * otherwise normalize independently and make visually-similar bars hide
   * real differences in the underlying numbers. Falls back to this
   * distribution's own min/max when omitted. */
  scaleMin?: number;
  scaleMax?: number;
}) {
  const { min, max, p10, p25, median, p75, p90 } = distribution;

  if (min === null || max === null || min === max) {
    return <p className="text-sm text-slate-400">Not enough history to show a distribution.</p>;
  }

  const axisMin = scaleMin ?? min;
  const axisMax = scaleMax ?? max;

  const toPct = (v: number) => ((v - axisMin) / (axisMax - axisMin)) * 100;
  const showZeroLine = axisMin < 0 && axisMax > 0;

  return (
    <div className="space-y-2">
      <div className="relative h-8 rounded bg-slate-900 border border-slate-800 overflow-hidden">
        {/* Faint gridlines at fixed axis fractions (not data-derived) — when
         * two bars share one scale (scaleMin/scaleMax passed in), these land
         * at the same physical position in both, making the shared axis
         * visually obvious rather than something you have to take on faith
         * from the numbers alone. */}
        {[25, 50, 75].map((pct) => (
          <div key={pct} className="absolute top-0 bottom-0 w-px bg-slate-700/40" style={{ left: `${pct}%` }} />
        ))}
        <div
          className="absolute top-0 bottom-0 bg-slate-700/50"
          style={{ left: `${toPct(p10 ?? min)}%`, right: `${100 - toPct(p90 ?? max)}%` }}
          title={`P10–P90: ${formatPct(p10)} to ${formatPct(p90)}`}
        />
        <div
          className="absolute top-0 bottom-0 bg-indigo-800/70"
          style={{ left: `${toPct(p25 ?? min)}%`, right: `${100 - toPct(p75 ?? max)}%` }}
          title={`P25–P75: ${formatPct(p25)} to ${formatPct(p75)}`}
        />
        {median !== null && (
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-indigo-300"
            style={{ left: `${toPct(median)}%` }}
            title={`Median: ${formatPct(median)}`}
          />
        )}
        {showZeroLine && (
          <div className="absolute top-0 bottom-0 w-px bg-slate-400" style={{ left: `${toPct(0)}%` }} title="0%" />
        )}
      </div>
      <div className="flex justify-between text-xs text-slate-400">
        <span>worst {formatPct(min)}</span>
        <span className="text-slate-300">median {formatPct(median)}</span>
        <span>best {formatPct(max)}</span>
      </div>
      {scaleMin !== undefined && scaleMax !== undefined && (axisMin !== min || axisMax !== max) && (
        <p className="text-[11px] text-slate-400">
          Shown on a shared scale ({formatPct(axisMin, 1)} to {formatPct(axisMax, 1)}) for direct comparison.
        </p>
      )}
    </div>
  );
}
