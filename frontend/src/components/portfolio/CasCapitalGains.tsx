import { Disclosure } from "@/components/fund/Disclosure";
import { StatCard } from "@/components/fund/StatCard";
import { formatRupees } from "@/lib/format";
import type { CASCapitalGainsSummary } from "@/types/cas";

/** Capital-gains tax classification for every still-held FIFO lot — what
 * LTCG/STCG tax would apply TODAY if sold, per analytics/capital_gains.py.
 * A factual "if sold today" statement only, never a suggestion to sell:
 * every bucket is shown as-is, including the ones this platform
 * deliberately can't put a number on (slab-rate-dependent, indeterminate)
 * rather than guessing. Renders nothing if there are no still-held,
 * priced lots at all. */
export function CasCapitalGains({ capitalGains }: { capitalGains: CASCapitalGainsSummary }) {
  const { by_bucket, total_tax_if_realized_today, equity_ltcg_exemption_note } = capitalGains;
  const totalLots = Object.values(by_bucket).reduce((sum, b) => sum + b.lot_count, 0);
  if (totalLots === 0) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-xs uppercase tracking-wide text-slate-500">Capital Gains (If Sold Today)</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Short-Term (STCG)"
          value={`${by_bucket.STCG.lot_count} lot${by_bucket.STCG.lot_count === 1 ? "" : "s"}`}
          hint={by_bucket.STCG.lot_count > 0 ? `Tax: ${formatRupees(by_bucket.STCG.tax_if_realized_today)}` : undefined}
        />
        <StatCard
          label="Long-Term (LTCG)"
          value={`${by_bucket.LTCG.lot_count} lot${by_bucket.LTCG.lot_count === 1 ? "" : "s"}`}
          hint={by_bucket.LTCG.lot_count > 0 ? `Tax: ${formatRupees(by_bucket.LTCG.tax_if_realized_today)}` : undefined}
        />
        <StatCard
          label="Slab-Rate Dependent"
          value={`${by_bucket.slab_rate_dependent.lot_count} lot${by_bucket.slab_rate_dependent.lot_count === 1 ? "" : "s"}`}
          hint="Debt-oriented — depends on your income-tax slab, not shown"
        />
        <StatCard
          label="Not Determinable"
          value={`${by_bucket.indeterminate.lot_count} lot${by_bucket.indeterminate.lot_count === 1 ? "" : "s"}`}
          hint="Category doesn't pin down an equity allocation — not guessed"
        />
      </div>

      <p className="text-sm text-slate-300">
        Total tax if every STCG/LTCG lot were sold today:{" "}
        <span className="font-mono tabular-nums">{formatRupees(total_tax_if_realized_today)}</span>
        {equity_ltcg_exemption_note && <span className="text-slate-500"> (before the annual LTCG exemption — see below)</span>}
      </p>

      <Disclosure label="How is this calculated, and what's left out?">
        <p className="text-sm text-slate-400">
          Each still-held lot (tracked FIFO, the same lot-by-lot accounting as Holding Period above) is classified
          as Short-Term or Long-Term Capital Gains under India&rsquo;s current mutual-fund tax rules, based on the
          scheme&rsquo;s regulatory equity-vs-debt category and how long that lot has been held. A loss is never
          taxed. This is a factual estimate, not tax advice — it never suggests selling anything.
        </p>
        {equity_ltcg_exemption_note && <p className="text-sm text-slate-400 mt-2">{equity_ltcg_exemption_note}</p>}
        <p className="text-sm text-slate-400 mt-2">
          &ldquo;Slab-Rate Dependent&rdquo; lots are debt-oriented holdings whose tax depends on your personal
          income-tax slab, which this tool doesn&rsquo;t know. &ldquo;Not Determinable&rdquo; lots are in categories
          (e.g. Balanced Advantage, Multi Asset, Gold) whose equity allocation isn&rsquo;t fixed by regulation, so no
          classification is guessed.
        </p>
      </Disclosure>
    </div>
  );
}
