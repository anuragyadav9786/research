import { AllocationBar } from "@/components/fund/AllocationBar";
import { Disclosure } from "@/components/fund/Disclosure";
import { formatNumber } from "@/lib/format";
import type { CASConcentrationSummary, CASPortfolioStructure as CASPortfolioStructureData } from "@/types/cas";

const HHI_LABELS: Record<string, string> = {
  diversified: "Diversified",
  moderate_concentration: "Moderate Concentration",
  high_concentration: "High Concentration",
};

function ConcentrationStat({ label, summary }: { label: string; summary: CASConcentrationSummary }) {
  return (
    <div className="rounded-lg border border-slate-800 p-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-lg font-semibold mt-1 text-slate-100">{formatNumber(summary.top5_pct, 1)}%</div>
      <div className="text-xs text-slate-500 mt-1">
        Top 5 · {HHI_LABELS[summary.hhi_label] ?? summary.hhi_label}
        {summary.count !== null && (
          <>
            {" "}
            · {summary.count} {summary.count === 1 ? "group" : "groups"}
          </>
        )}
      </div>
    </div>
  );
}

/** Portfolio Analysis §7/§8: asset allocation, equity style, and
 * concentration by scheme/AMC/category, computed from a CAS's currently-
 * held, ISIN-matched positions (see CasUploadPanel.tsx). Reuses the same
 * AllocationBar the single-fund and manual Portfolio Analysis pages
 * already use, so the visual language stays consistent. */
export function CasPortfolioStructure({ structure }: { structure: CASPortfolioStructureData }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Asset Allocation</h3>
        <AllocationBar slices={structure.asset_allocation} />
      </div>

      {structure.equity_style_allocation.length > 0 && (
        <div>
          <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">
            Equity Style <span className="normal-case text-slate-600">(% of whole portfolio, not just equity)</span>
          </h3>
          <AllocationBar slices={structure.equity_style_allocation} />
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <ConcentrationStat label="By Scheme" summary={structure.scheme_concentration} />
        <ConcentrationStat label="By AMC" summary={structure.amc_concentration} />
        <ConcentrationStat label="By Category" summary={structure.category_concentration} />
      </div>

      <Disclosure label="Allocation by AMC &amp; Category" expandedLabel="Hide AMC &amp; Category breakdown">
        <div className="space-y-4 mt-1">
          <div>
            <h4 className="text-xs uppercase tracking-wide text-slate-500 mb-2">By AMC</h4>
            <AllocationBar slices={structure.amc_allocation} />
          </div>
          <div>
            <h4 className="text-xs uppercase tracking-wide text-slate-500 mb-2">By Category</h4>
            <AllocationBar slices={structure.category_allocation} />
          </div>
        </div>
      </Disclosure>

      <Disclosure label="What is HHI / concentration?">
        <p className="text-sm text-slate-400">
          The Herfindahl-Hirschman Index (HHI) measures how concentrated your portfolio is — a higher score means
          your money is spread across fewer, larger positions. It&rsquo;s the same methodology used in antitrust
          market-concentration analysis, adapted here to portfolio weights: a portfolio split equally across N
          holdings scores 10,000/N. Below 1,500 is considered diversified, 1,500&ndash;2,500 moderate concentration,
          and above 2,500 high concentration — a label, not a verdict.
        </p>
      </Disclosure>
    </div>
  );
}
