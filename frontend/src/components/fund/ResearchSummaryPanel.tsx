import type { ResearchSummaryPoint } from "@/lib/researchSummary";

/** Renders the template-generated research summary as a coherent set of
 * short sections rather than a chart-by-chart recap — the brief's
 * "convert multiple charts into a coherent research narrative." Always
 * visible (no button, no API key dependency); see researchSummary.ts for
 * why every sentence here is directly traceable to one already-computed
 * API field. */
export function ResearchSummaryPanel({ points }: { points: ResearchSummaryPoint[] }) {
  return (
    <div className="rounded-lg border border-slate-800 p-4 sm:p-6 space-y-4">
      {points.map((point) => (
        <div key={point.heading}>
          <h3 className="text-xs uppercase tracking-wide text-slate-500">{point.heading}</h3>
          <p className="text-sm text-slate-300 mt-1">{point.sentence}</p>
        </div>
      ))}
      <p className="text-xs text-slate-600 border-t border-slate-900 pt-3">
        This summary states what the historical data shows — it is not a recommendation to buy, hold, or sell, and
        past behaviour does not guarantee future results.
      </p>
    </div>
  );
}
