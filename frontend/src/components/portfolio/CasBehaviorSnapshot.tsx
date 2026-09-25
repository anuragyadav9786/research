import { Disclosure } from "@/components/fund/Disclosure";
import { StatCard } from "@/components/fund/StatCard";
import { formatDate, formatPct, formatRupees } from "@/lib/format";
import type { CASInvestorBehavior, CASPortfolioComplexity } from "@/types/cas";

const COMPLEXITY_LABEL_CLASS: Record<string, string> = {
  Simple: "text-emerald-400",
  Moderate: "text-slate-200",
  Complex: "text-amber-400",
  "Highly Complex": "text-rose-400",
};

/** Portfolio Analysis §complexity + investor behavior: how many distinct
 * moving parts the current portfolio spans, and purely factual activity
 * metrics (recorded span, switch/redemption ratios). Deliberately no
 * "return-chasing" or "panic-selling" inference here — see
 * cas_portfolio_service.py's own module docstring for why that's out of
 * scope. Renders nothing if there's no matched, priced holding at all. */
export function CasBehaviorSnapshot({
  complexity,
  behavior,
}: {
  complexity: CASPortfolioComplexity;
  behavior: CASInvestorBehavior;
}) {
  if (complexity.scheme_count === 0 && behavior.investing_since === null) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-xs uppercase tracking-wide text-slate-500">Portfolio Snapshot</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Complexity"
          value={complexity.complexity_label}
          valueClassName={COMPLEXITY_LABEL_CLASS[complexity.complexity_label] ?? "text-slate-200"}
          hint={`${complexity.scheme_count} scheme${complexity.scheme_count === 1 ? "" : "s"} · ${complexity.amc_count} AMC${complexity.amc_count === 1 ? "" : "s"}`}
        />
        <StatCard
          label="Folios"
          value={String(complexity.folio_count)}
          hint={
            complexity.folio_count > complexity.scheme_count
              ? "Includes a scheme held across more than one folio"
              : "One folio per scheme"
          }
        />
        <StatCard
          label="Investing Since"
          value={behavior.investing_since !== null ? formatDate(behavior.investing_since) : "N/A"}
          hint={
            behavior.investing_span_days !== null
              ? `${behavior.investing_span_days} days of recorded activity`
              : undefined
          }
        />
        <StatCard
          label="Moved / Redeemed"
          value={behavior.switch_ratio_pct !== null ? formatPct(behavior.switch_ratio_pct) : "N/A"}
          hint={
            behavior.redemption_ratio_pct !== null
              ? `Switched · ${formatRupees(behavior.total_redeemed_amount)} (${formatPct(behavior.redemption_ratio_pct)}) redeemed`
              : undefined
          }
        />
      </div>
      <Disclosure label="What do these mean?">
        <p className="text-sm text-slate-400">
          Complexity counts the distinct schemes, AMCs, and categories your current holdings span — a simple,
          transparent indicator of how many moving parts you have to track, not a judgment of whether that&rsquo;s
          too many. Folios shows how many separate registrations back those holdings; more folios than schemes means
          the same fund is held under more than one registration.
        </p>
        <p className="text-sm text-slate-400 mt-2">
          &ldquo;Moved / Redeemed&rdquo; is the share of total invested capital that has since moved between schemes
          (switches/STP) or come back to you (redemptions/SWP/dividends) — purely what happened, not a read on why.
        </p>
      </Disclosure>
    </div>
  );
}
