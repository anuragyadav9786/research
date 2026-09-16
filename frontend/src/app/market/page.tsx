import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { listMarketRegimes } from "@/lib/api";
import { formatDate } from "@/lib/format";

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

const REGIME_TYPE_COLORS: Record<string, string> = {
  bull: "bg-emerald-900/60 text-emerald-200",
  bear: "bg-rose-900/60 text-rose-200",
  correction: "bg-amber-900/60 text-amber-200",
  high_volatility: "bg-violet-900/60 text-violet-200",
};

export const metadata = { title: "Market Intelligence — ThinkFin" };

export const dynamic = "force-dynamic";

export default async function MarketIntelligencePage() {
  const regimes = await listMarketRegimes();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="market" />

      <main className="px-8 py-10 max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Market Regimes</h1>
          <p className="text-slate-400 text-sm mt-1">
            Historical market-cycle windows used to evaluate fund behaviour on each fund&apos;s page.
          </p>
          <p className="text-xs text-slate-600 mt-2 max-w-2xl">
            In the current sample dataset these are illustrative date windows derived from the Phase 2
            synthetic seed data&apos;s own shape, not verified real-world market classifications. Sector
            trends and a broader risk environment view are not built yet.
          </p>
        </div>

        {regimes.length === 0 ? (
          <p className="text-sm text-slate-500">No market regimes defined yet.</p>
        ) : (
          <div className="rounded-lg border border-slate-800 divide-y divide-slate-800">
            {regimes.map((r) => (
              <div key={r.id} className="flex items-center justify-between px-5 py-4">
                <div>
                  <div className="font-medium">{r.name.replace(/^Sample Regime — /, "")}</div>
                  <div className="text-sm text-slate-500 mt-0.5">
                    {formatDate(r.start_date)} – {r.end_date ? formatDate(r.end_date) : "present"}
                  </div>
                </div>
                <span
                  className={`text-xs px-2.5 py-1 rounded-full ${
                    REGIME_TYPE_COLORS[r.regime_type] ?? "bg-slate-800 text-slate-300"
                  }`}
                >
                  {REGIME_TYPE_LABELS[r.regime_type] ?? r.regime_type}
                </span>
              </div>
            ))}
          </div>
        )}

        <p className="text-xs text-slate-500">
          See how any fund performed during these periods on its own research page (Market-Cycle
          Behaviour section) — start from{" "}
          <Link href="/research" className="text-indigo-500 hover:text-indigo-600">
            Research
          </Link>
          .
        </p>
      </main>
    </div>
  );
}
