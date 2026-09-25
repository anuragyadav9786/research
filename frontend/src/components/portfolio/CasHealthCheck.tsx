import type { CASHealthCheck as CASHealthCheckData } from "@/types/cas";

/** Portfolio Analysis §"Portfolio Health Check": a compact, deterministic
 * summary of how complete this analysis is and how many observations
 * were flagged below — never a graded score or verdict on the portfolio
 * itself, and never alarmist coloring (no red — "significant" uses the
 * same amber the rest of this app reserves for "worth a look," not
 * "danger"). See CasInsightsList for the observations themselves. */
export function CasHealthCheck({ healthCheck }: { healthCheck: CASHealthCheckData }) {
  if (healthCheck.total_referenced_scheme_count === 0) return null;

  const badges = [
    { count: healthCheck.significant_count, label: "significant", className: "bg-amber-950/60 text-amber-300 border-amber-800/60" },
    { count: healthCheck.notable_count, label: "notable", className: "bg-indigo-950/60 text-indigo-300 border-indigo-800/60" },
    {
      count: healthCheck.informational_count,
      label: "informational",
      className: "bg-slate-900 text-slate-400 border-slate-800",
    },
  ].filter((b) => b.count > 0);

  return (
    <div className="rounded-lg border border-slate-800 p-4">
      <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Portfolio Health Check</h3>
      <p className="text-sm text-slate-300">{healthCheck.summary}</p>
      {badges.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {badges.map((b) => (
            <span
              key={b.label}
              className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs ${b.className}`}
            >
              {b.count} {b.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
