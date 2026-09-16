import { formatDate, formatPct, signColorClass } from "@/lib/format";
import type { RegimeBehavior } from "@/types/marketRegime";

const REGIME_TYPE_LABELS: Record<string, string> = {
  bull: "Bull",
  bear: "Bear",
  correction: "Correction",
  high_volatility: "High Volatility",
  low_volatility: "Low Volatility",
  rising_rates: "Rising Rates",
  falling_rates: "Falling Rates",
  high_inflation: "High Inflation",
  low_inflation: "Low Inflation",
};

export function MarketRegimeTable({ regimes }: { regimes: RegimeBehavior[] }) {
  return (
    <div className="space-y-3">
      {regimes.map((r) => (
        <div key={r.regime_name} className="rounded-lg border border-slate-800 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div>
              <span className="text-sm font-medium">{r.regime_name.replace(/^Sample Regime — /, "")}</span>
              <span className="text-xs text-slate-500 ml-2">
                {REGIME_TYPE_LABELS[r.regime_type] ?? r.regime_type} · {formatDate(r.start_date)} –{" "}
                {r.end_date ? formatDate(r.end_date) : "present"}
              </span>
            </div>
            {r.fund_available && (
              <span className={`text-sm font-medium ${signColorClass(r.fund_return_pct)}`}>
                {formatPct(r.fund_return_pct)}
                {r.benchmark_available && (
                  <span className="text-slate-500 font-normal"> vs {formatPct(r.benchmark_return_pct)}</span>
                )}
              </span>
            )}
          </div>
          <p className="text-sm text-slate-400">{r.summary}</p>
        </div>
      ))}
    </div>
  );
}
