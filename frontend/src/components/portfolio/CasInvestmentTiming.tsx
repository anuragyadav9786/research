import { AllocationBar } from "@/components/fund/AllocationBar";
import { Disclosure } from "@/components/fund/Disclosure";
import { formatRupees } from "@/lib/format";
import type { CASInvestmentTiming as CASInvestmentTimingData } from "@/types/cas";

const REGIME_TYPE_LABELS: Record<string, string> = {
  bull: "Bull",
  correction: "Correction",
  high_volatility: "High Volatility",
  crash: "Crash",
  recovery: "Recovery",
};

/** Portfolio Analysis §14: how much money went in during each known
 * market regime — purely descriptive, never a claim about whether the
 * timing was good or bad (no buy/sell framing, per the module's
 * constraint). Weights are recomputed here across ALL purchases
 * (classified + unclassified), not just the classified ones the backend's
 * own weight_pct is based on, so the bar never silently omits a slice of
 * real money. Renders nothing if there's nothing to classify at all. */
export function CasInvestmentTiming({ timing }: { timing: CASInvestmentTimingData }) {
  const totalInvested = timing.total_classified_invested_amount + timing.unclassified_invested_amount;
  if (totalInvested <= 0) return null;

  const slices = [
    ...timing.regime_breakdown.map((r) => ({
      label: REGIME_TYPE_LABELS[r.regime_type] ?? r.regime_name,
      value: r.invested_amount,
      weight_pct: (r.invested_amount / totalInvested) * 100,
    })),
    ...(timing.unclassified_invested_amount > 0
      ? [
          {
            label: "Unclassified",
            value: timing.unclassified_invested_amount,
            weight_pct: (timing.unclassified_invested_amount / totalInvested) * 100,
          },
        ]
      : []),
  ];

  return (
    <div className="space-y-2">
      <h3 className="text-xs uppercase tracking-wide text-slate-500">Investment Timing</h3>
      <AllocationBar slices={slices} />
      {timing.unclassified_purchase_count > 0 && (
        <p className="text-xs text-slate-500">
          {timing.unclassified_purchase_count} purchase{timing.unclassified_purchase_count === 1 ? "" : "s"} (
          {formatRupees(timing.unclassified_invested_amount)}) fell outside every date window this platform has a
          market-regime classification for.
        </p>
      )}
      <Disclosure label="What are these market regimes?">
        <p className="text-sm text-slate-400">{timing.methodology_note}</p>
      </Disclosure>
    </div>
  );
}
