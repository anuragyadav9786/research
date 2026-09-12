import { formatNumber, formatPct, signColorClass } from "@/lib/format";
import type { ScenarioResult } from "@/types/stressTest";

export function StressTestPanel({ scenarios }: { scenarios: ScenarioResult[] }) {
  return (
    <div className="space-y-3">
      {scenarios.map((s) => (
        <div key={s.scenario_id} className="rounded-lg border border-neutral-800 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
            <span className="text-sm font-medium">{s.name}</span>
            {s.available ? (
              <span className={`text-sm font-semibold ${signColorClass(s.estimated_impact_pct)}`}>
                {formatPct(s.estimated_impact_pct)}
              </span>
            ) : (
              <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-800 text-neutral-400">Not modeled</span>
            )}
          </div>
          <p className="text-sm text-neutral-500">{s.description}</p>
          {s.available ? (
            <p className="text-xs text-neutral-600 mt-1.5">
              {s.shock_type === "index"
                ? `Based on this fund's beta (${formatNumber(s.exposure_pct, 3)}) to its benchmark.`
                : `Based on ${formatNumber(s.exposure_pct, 1)}% disclosed exposure to this segment.`}
            </p>
          ) : (
            <p className="text-xs text-amber-500/80 mt-1.5">{s.reason}</p>
          )}
        </div>
      ))}
    </div>
  );
}
