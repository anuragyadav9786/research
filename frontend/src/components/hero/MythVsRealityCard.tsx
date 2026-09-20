import { AlertTriangle, TrendingDown } from "lucide-react";

import { DistributionBar } from "@/components/fund/DistributionBar";
import { formatLakh, formatPct } from "@/lib/format";
import type { RollingReturnDistribution } from "@/types/fund";

// A round, easy-to-hold-in-your-head principal for the rupee-terms
// translation below — ₹10 lakh, not this fund's actual AUM or any real
// investor's holding. Applying a real, computed drawdown percentage to an
// illustrative principal is standard practice for making a percentage
// concrete; the copy is explicit that it's hypothetical, not a real
// outcome.
const ILLUSTRATIVE_PRINCIPAL = 1_000_000;

export interface MythVsRealityData {
  id: number;
  schemeName: string;
  category: string;
  /** Point-to-point 3Y CAGR — "the myth": a single snapshot that depends
   * entirely on the day you happen to measure from. */
  cagr3y: number | null;
  maxDrawdown: number | null;
  /** Null when the fund is still underwater (see `recovered`) rather than
   * when data is simply missing — those two cases read differently in the
   * copy below, never collapsed into one "—". */
  recovered: boolean | null;
  recoveryDurationDays: number | null;
  distribution: RollingReturnDistribution;
}

/** The homepage's "Myth vs. Reality" anchor — one real fund's misleadingly
 * clean point-to-point CAGR next to what actually happened to an investor
 * holding it: peak drawdown, how long recovery took (or didn't), and the
 * full spread of rolling 3Y outcomes. Every figure here comes from this
 * platform's own computed returns/drawdown/rolling-return endpoints for a
 * real, currently-onboarded fund — never a placeholder or fabricated
 * value; a figure that isn't available renders as "—" rather than 0. */
export function MythVsRealityCard({ fund }: { fund: MythVsRealityData }) {
  const { min, median, max } = fund.distribution;
  const troughValue = fund.maxDrawdown !== null ? ILLUSTRATIVE_PRINCIPAL * (1 + fund.maxDrawdown / 100) : null;

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-6 sm:p-8">
      <p className="text-xs uppercase tracking-wide text-white/50">{fund.schemeName}</p>
      <p className="text-xs text-white/50 mt-0.5">{fund.category}</p>

      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-6 sm:gap-8 sm:divide-x sm:divide-[var(--border-subtle)]">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-white/50">What Standard Portals Show</p>
          <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-white/5 px-4 py-2">
            <span className="font-mono tabular-nums text-2xl font-semibold text-white/90">
              {formatPct(fund.cagr3y, 1)}
            </span>
            <span className="text-xs text-white/50">p.a. (3Y)</span>
          </div>
          <p className="mt-3 text-sm text-white/50">
            A single point-to-point snapshot — feels safe and clean, but depends entirely on the exact day you
            measure from.
          </p>
        </div>

        <div className="sm:pl-8">
          <p className="text-xs font-medium uppercase tracking-wide text-white/50">
            What Actually Happened (ThinkFin NAV Reality)
          </p>

          <div className="mt-3 flex items-start gap-2">
            <TrendingDown aria-hidden="true" className="h-4 w-4 text-rose-400 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-white/80">
              Peak drawdown{" "}
              <span className="font-mono tabular-nums font-semibold text-rose-400">
                {formatPct(fund.maxDrawdown, 1)}
              </span>
              {fund.recovered === true && fund.recoveryDurationDays != null && (
                <> — recovery took {fund.recoveryDurationDays} days.</>
              )}
              {fund.recovered === false && <> — investors are still waiting to break even.</>}
            </p>
          </div>

          <div className="mt-4 flex items-start gap-2">
            <AlertTriangle aria-hidden="true" className="h-4 w-4 text-amber-400 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-white/80">
                Rolling 3Y return: min{" "}
                <span className="font-mono tabular-nums font-semibold text-rose-400">{formatPct(min, 2)}</span> ·
                median <span className="font-mono tabular-nums font-semibold text-white">{formatPct(median, 2)}</span>{" "}
                · max <span className="font-mono tabular-nums font-semibold text-emerald-400">{formatPct(max, 2)}</span>
              </p>
              <div className="mt-2">
                <DistributionBar distribution={fund.distribution} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {fund.maxDrawdown !== null && (
        <div className="mt-6 rounded-lg border border-[var(--border-subtle)] bg-white/5 p-4 sm:p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-white/50">In Rupee Terms</p>
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <div className="text-xs text-white/50">Hypothetical Investment</div>
              <div className="font-mono tabular-nums text-white font-semibold mt-0.5">
                {formatLakh(ILLUSTRATIVE_PRINCIPAL)}
              </div>
            </div>
            <div>
              <div className="text-xs text-white/50">Worst Observed Drawdown</div>
              <div className="font-mono tabular-nums text-rose-400 font-semibold mt-0.5">
                {formatPct(fund.maxDrawdown, 1)}
              </div>
            </div>
            <div>
              <div className="text-xs text-white/50">Approx. Value at Trough</div>
              <div className="font-mono tabular-nums text-rose-400 font-semibold mt-0.5">{formatLakh(troughValue)}</div>
            </div>
            <div>
              <div className="text-xs text-white/50">Recovery Period</div>
              <div className="font-mono tabular-nums text-white font-semibold mt-0.5">
                {fund.recovered === true && fund.recoveryDurationDays != null
                  ? `${fund.recoveryDurationDays} days`
                  : fund.recovered === false
                    ? "Not yet recovered"
                    : "—"}
              </div>
            </div>
          </div>
          <p className="mt-3 text-sm text-white/60">
            A strong long-term return can coexist with significant temporary losses. ThinkFin helps you understand
            the journey, not just the destination.
          </p>
          <p className="mt-2 text-[11px] text-white/40">
            Illustrative only — assumes a lump-sum investment at the fund&rsquo;s pre-drawdown peak. Not an actual
            investment outcome, projection, or recommendation.
          </p>
        </div>
      )}

      <p className="mt-6 pt-6 border-t border-[var(--border-subtle)] text-sm text-white/50">
        Point-to-point returns depend entirely on the day you measure. Rolling consistency tells you what holding
        the fund actually felt like.
      </p>
    </div>
  );
}
