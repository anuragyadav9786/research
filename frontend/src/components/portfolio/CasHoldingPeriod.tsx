import { AllocationBar } from "@/components/fund/AllocationBar";
import { Disclosure } from "@/components/fund/Disclosure";
import type { CASHoldingPeriodSummary } from "@/types/cas";

function daysLabel(days: number): string {
  if (days < 365) return `${days} days`;
  const years = days / 365;
  return `${years.toFixed(1)} years`;
}

/** Portfolio Analysis §12 (Holding Period Analysis): how long money has
 * actually been held, computed from FIFO lot accounting — the still-open
 * (unsold) lots' value-weighted age, plus how long past sales were held
 * for. Purely descriptive (holding period, not a tax or hold/sell
 * recommendation) per the module's no-buy/sell-engine constraint. */
export function CasHoldingPeriod({ holdingPeriod }: { holdingPeriod: CASHoldingPeriodSummary }) {
  const hasOpenData = holdingPeriod.open_value_by_bucket.length > 0;
  const hasRealizedData = holdingPeriod.realized_consumption_count > 0;

  if (!hasOpenData && !hasRealizedData) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-xs uppercase tracking-wide text-slate-500">Holding Period</h3>

      {hasOpenData && (
        <div>
          <p className="text-sm text-slate-300">
            Current holdings have been held for{" "}
            <span className="font-mono tabular-nums">
              {holdingPeriod.open_weighted_avg_days !== null ? daysLabel(holdingPeriod.open_weighted_avg_days) : "—"}
            </span>{" "}
            on average, value-weighted.
          </p>
          <div className="mt-2">
            <AllocationBar slices={holdingPeriod.open_value_by_bucket} />
          </div>
        </div>
      )}

      {hasRealizedData && (
        <p className="text-xs text-slate-500">
          {holdingPeriod.realized_consumption_count} past sale{holdingPeriod.realized_consumption_count === 1 ? "" : "s"}{" "}
          (redemptions/switch-outs) were held for{" "}
          {holdingPeriod.realized_avg_days !== null ? daysLabel(holdingPeriod.realized_avg_days) : "—"} on average
          (median {holdingPeriod.realized_median_days !== null ? daysLabel(holdingPeriod.realized_median_days) : "—"}).
        </p>
      )}

      <Disclosure label="What is holding period, and why does it matter?">
        <p className="text-sm text-slate-400">
          How long each rupee has actually stayed invested, tracked lot-by-lot in purchase order (the same
          first-in-first-out convention CAS statements themselves use for redemptions). It&rsquo;s a description of
          past behavior, not a suggestion to hold or sell — tax treatment and ideal holding periods vary by scheme
          type and your own situation.
        </p>
      </Disclosure>
    </div>
  );
}
