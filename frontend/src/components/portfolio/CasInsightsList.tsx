import type { CASInsight, CASInsightSeverity } from "@/types/cas";

const SEVERITY_STYLES: Record<CASInsightSeverity, string> = {
  significant: "border-amber-800/60 bg-amber-950/30",
  notable: "border-indigo-800/60 bg-indigo-950/20",
  informational: "border-slate-800 bg-slate-900/40",
};

const SEVERITY_DOT: Record<CASInsightSeverity, string> = {
  significant: "bg-amber-400",
  notable: "bg-indigo-400",
  informational: "bg-slate-500",
};

const CATEGORY_LABELS: Record<string, string> = {
  concentration: "Concentration",
  overlap: "Fund Overlap",
  data_completeness: "Data Completeness",
  investment_timing: "Investment Timing",
  sip_consistency: "SIP Consistency",
  complexity: "Complexity",
  holding_period: "Holding Period",
  realized_performance: "Realized Performance",
};

/** Portfolio Analysis §"Actionable Insights": evidence-based observations
 * only — every message here cites a number computed elsewhere in this
 * report. Never a buy/sell/hold recommendation and never alarmist
 * wording (severity is the neutral informational/notable/significant
 * scale, not a warning level) — see backend/app/services/
 * cas_insights_service.py for the full rule set and reasoning. */
export function CasInsightsList({ insights }: { insights: CASInsight[] }) {
  if (insights.length === 0) return null;

  return (
    <div>
      <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Observations</h3>
      <ul className="space-y-2">
        {insights.map((insight, i) => (
          <li key={i} className={`rounded-md border px-3 py-2 text-sm ${SEVERITY_STYLES[insight.severity]}`}>
            <div className="flex items-start gap-2">
              <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${SEVERITY_DOT[insight.severity]}`} />
              <div>
                <span className="text-[11px] uppercase tracking-wide text-slate-500">
                  {CATEGORY_LABELS[insight.category] ?? insight.category}
                </span>
                <p className="text-slate-300 mt-0.5">{insight.message}</p>
              </div>
            </div>
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-600 mt-2">
        These are observations about what the data shows, not investment advice or a suggestion to buy, sell, or
        hold anything.
      </p>
    </div>
  );
}
