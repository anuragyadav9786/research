import { Disclosure } from "@/components/fund/Disclosure";
import { StatCard } from "@/components/fund/StatCard";
import { formatDate, formatPct, signColorClass } from "@/lib/format";
import type { CASTimeWeightedReturn } from "@/types/cas";

/** Portfolio Analysis §6: Time-Weighted Return, volatility, and max
 * drawdown of the portfolio's own actual value over time — reconstructed
 * from real per-scheme unit holdings and NAV history (see
 * analytics/portfolio_valuation.py), not a hypothetical fixed-weight
 * blend. Renders nothing if no matched scheme could be priced at all,
 * rather than a card full of "N/A". */
export function CasTimeWeightedReturn({ twr }: { twr: CASTimeWeightedReturn }) {
  if (twr.priced_scheme_count === 0) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-xs uppercase tracking-wide text-slate-500">Return Consistency</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Time-Weighted Return"
          value={twr.annualized_twr_pct !== null ? formatPct(twr.annualized_twr_pct) : "N/A"}
          valueClassName={twr.annualized_twr_pct !== null ? signColorClass(twr.annualized_twr_pct) : "text-slate-600"}
          hint={
            twr.cumulative_twr_pct !== null
              ? `${formatPct(twr.cumulative_twr_pct)} total, ${formatDate(twr.start_date)} to ${formatDate(twr.end_date)}`
              : "Not enough priced history to solve for a rate"
          }
        />
        <StatCard
          label="Volatility"
          value={twr.volatility_pct !== null ? `${twr.volatility_pct.toFixed(1)}%` : "N/A"}
          hint="Annualized, from the same period"
        />
        <StatCard
          label="Max Drawdown"
          value={twr.max_drawdown_pct !== null ? formatPct(twr.max_drawdown_pct) : "N/A"}
          valueClassName={twr.max_drawdown_pct !== null ? signColorClass(twr.max_drawdown_pct) : "text-slate-600"}
          hint={
            twr.drawdown_trough_date !== null
              ? twr.drawdown_recovered
                ? `Recovered by ${formatDate(twr.drawdown_recovery_date)}`
                : `Not yet recovered as of ${formatDate(twr.end_date)}`
              : undefined
          }
        />
        <StatCard
          label="Coverage"
          value={`${twr.priced_scheme_count} scheme${twr.priced_scheme_count === 1 ? "" : "s"}`}
          hint="With price history available"
        />
      </div>
      <Disclosure label="What is Time-Weighted Return, and how does it differ from XIRR?">
        <p className="text-sm text-slate-400">
          Time-Weighted Return (TWR) measures how the portfolio itself performed, stripped of when you happened to
          put money in or take it out — unlike the Portfolio XIRR above, which is money-weighted and reflects your
          own contribution timing. A large SIP right before a market dip lowers your XIRR but doesn&rsquo;t affect
          TWR at all.
        </p>
        <p className="text-sm text-slate-400 mt-2">
          Volatility and max drawdown are computed on this same cash-flow-neutral return series, so they describe
          how choppy the ride was, not how your specific contributions timed it. Only schemes with price history in
          our database are included — schemes we&rsquo;ve never priced can&rsquo;t be placed in this reconstruction
          at all.
        </p>
      </Disclosure>
    </div>
  );
}
