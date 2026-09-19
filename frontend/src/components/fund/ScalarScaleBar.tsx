import type { MetricZone } from "@/lib/metricInterpretation";

/** Tier 2 of the progressive-disclosure metric system — a single value
 * positioned on a fixed, labeled scale (as opposed to DistributionBar,
 * which plots a full percentile spread). The colored zones underneath are
 * the same heuristic bands `sentence` in Tier 1 already put into words;
 * this just makes them visually scannable without reading the text. */
export function ScalarScaleBar({
  value,
  scaleMin,
  scaleMax,
  zones,
  formatValue,
}: {
  value: number;
  scaleMin: number;
  scaleMax: number;
  zones: MetricZone[];
  formatValue: (v: number) => string;
}) {
  const toPct = (v: number) => (Math.min(scaleMax, Math.max(scaleMin, v)) - scaleMin) / (scaleMax - scaleMin) * 100;
  const markerPct = toPct(value);

  let zoneStart = scaleMin;
  const segments = zones.map((z) => {
    const start = toPct(zoneStart);
    const end = toPct(z.to);
    zoneStart = z.to;
    return { ...z, startPct: start, widthPct: end - start };
  });

  return (
    <div className="space-y-1">
      <div className="relative h-2 rounded-full overflow-hidden flex">
        {segments.map((seg) => (
          <div
            key={seg.label}
            className={seg.colorClass}
            style={{ width: `${seg.widthPct}%` }}
            title={`${seg.label}: up to ${formatValue(seg.to)}`}
          />
        ))}
      </div>
      <div className="relative h-0">
        <div
          className="absolute -top-[14px] h-3 w-0.5 -translate-x-1/2 bg-white"
          style={{ left: `${markerPct}%` }}
          title={formatValue(value)}
        />
      </div>
      <div className="flex justify-between text-[11px] text-slate-500">
        <span>{formatValue(scaleMin)}</span>
        <span>{formatValue(scaleMax)}</span>
      </div>
    </div>
  );
}
