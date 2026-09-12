import Link from "next/link";
import { notFound } from "next/navigation";

import {
  ApiError,
  getFund,
  getFundDrawdown,
  getFundMarketRegimes,
  getFundNavHistory,
  getFundPortfolio,
  getFundReturns,
  getFundRisk,
  getFundRollingReturns,
  getFundStressTest,
} from "@/lib/api";
import { formatDate, formatNav, formatNumber, formatPct, signColorClass } from "@/lib/format";
import { AllocationBar } from "@/components/fund/AllocationBar";
import { DistributionBar } from "@/components/fund/DistributionBar";
import { HoldingsTable } from "@/components/fund/HoldingsTable";
import { MarketRegimeTable } from "@/components/fund/MarketRegimeTable";
import { NavChart } from "@/components/fund/NavChart";
import { StatCard } from "@/components/fund/StatCard";
import { StressTestPanel } from "@/components/fund/StressTestPanel";
import type { DrawdownResponse, NavHistoryResponse, Option, Plan, ReturnsResponse, RiskResponse, RollingReturnsResponse } from "@/types/fund";
import type { MarketRegimeBehaviorResponse } from "@/types/marketRegime";
import type { StressTestResponse } from "@/types/stressTest";

const HHI_LABELS: Record<string, string> = {
  diversified: "Diversified",
  moderate_concentration: "Moderate Concentration",
  high_concentration: "High Concentration",
};

const RETURN_WINDOW_LABELS: Record<string, string> = { "1y": "1Y", "3y": "3Y", "5y": "5Y", "7y": "7Y", "10y": "10Y" };
const ROLLING_WINDOW_OPTIONS = [1, 3, 5];

export default async function FundDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ fundId: string }>;
  searchParams: Promise<{ plan?: string; option?: string; window?: string }>;
}) {
  const { fundId: fundIdParam } = await params;
  const fundId = Number(fundIdParam);
  if (!Number.isInteger(fundId)) notFound();

  const sp = await searchParams;
  const plan: Plan = sp.plan === "regular" ? "regular" : "direct";
  const option: Option = sp.option === "idcw" ? "idcw" : "growth";
  const windowYears = ROLLING_WINDOW_OPTIONS.includes(Number(sp.window)) ? Number(sp.window) : 3;

  let fund;
  try {
    fund = await getFund(fundId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  // Portfolio is variant-independent (holdings are the same across
  // plan/option), so it's fetched separately and renders even if the
  // requested plan/option combination doesn't exist.
  const portfolio = await getFundPortfolio(fundId);

  const variantParams = { plan, option };
  let returns: ReturnsResponse | null = null;
  let risk: RiskResponse | null = null;
  let rolling: RollingReturnsResponse | null = null;
  let drawdown: DrawdownResponse | null = null;
  let navHistory: NavHistoryResponse | null = null;
  let marketRegimes: MarketRegimeBehaviorResponse | null = null;
  let stressTest: StressTestResponse | null = null;
  let variantError: string | null = null;

  try {
    [returns, risk, rolling, drawdown, navHistory, marketRegimes, stressTest] = await Promise.all([
      getFundReturns(fundId, variantParams),
      getFundRisk(fundId, variantParams),
      getFundRollingReturns(fundId, { ...variantParams, window_years: windowYears }),
      getFundDrawdown(fundId, variantParams),
      getFundNavHistory(fundId, variantParams),
      getFundMarketRegimes(fundId, variantParams),
      getFundStressTest(fundId, variantParams),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      variantError = `This fund has no ${plan}/${option} variant.`;
    } else {
      throw err;
    }
  }

  const currentVariant = fund.variants.find((v) => v.plan === plan && v.option === option);
  const availablePlans = new Set(fund.variants.map((v) => v.plan));
  const availableOptions = new Set(fund.variants.filter((v) => v.plan === plan).map((v) => v.option));

  function urlFor(overrides: { plan?: Plan; option?: Option; window?: number }) {
    const qs = new URLSearchParams({
      plan: overrides.plan ?? plan,
      option: overrides.option ?? option,
      window: String(overrides.window ?? windowYears),
    });
    return `/research/${fundId}?${qs.toString()}`;
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-8 py-4 flex items-center justify-between">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          ThinkFin
        </Link>
        <nav className="flex gap-6 text-sm text-neutral-400">
          <Link href="/" className="hover:text-neutral-100">Dashboard</Link>
          <Link href="/research" className="hover:text-neutral-100">Research</Link>
          <Link href="/research/compare" className="hover:text-neutral-100">Compare</Link>
          <Link href="/portfolio" className="hover:text-neutral-100">Portfolio</Link>
          <Link href="/market" className="hover:text-neutral-100">Market Intelligence</Link>
        </nav>
      </header>

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-8">
        <div className="flex items-start justify-between">
          <div>
            <Link href="/research" className="text-sm text-neutral-500 hover:text-neutral-300">
              ← Back to Research
            </Link>
            <h1 className="text-2xl font-semibold mt-2">{fund.scheme_name}</h1>
            <p className="text-neutral-400 text-sm mt-1">
              {fund.amc_name} · {fund.category}
              {fund.benchmark_name && <> · Benchmark: {fund.benchmark_name}</>}
            </p>
          </div>
          <Link
            href={`/research/compare?a=${fundId}`}
            className="text-sm rounded-md border border-neutral-800 px-3 py-1.5 text-neutral-400 hover:text-neutral-100 hover:border-neutral-700 whitespace-nowrap"
          >
            Compare with…
          </Link>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <div className="flex rounded-md border border-neutral-800 overflow-hidden text-sm">
            {(["direct", "regular"] as Plan[]).map((p) => (
              <Link
                key={p}
                href={urlFor({ plan: p })}
                aria-disabled={!availablePlans.has(p)}
                className={`px-3 py-1.5 capitalize ${
                  p === plan
                    ? "bg-cyan-900/60 text-cyan-100"
                    : availablePlans.has(p)
                      ? "hover:bg-neutral-900 text-neutral-300"
                      : "text-neutral-700 pointer-events-none"
                }`}
              >
                {p}
              </Link>
            ))}
          </div>
          <div className="flex rounded-md border border-neutral-800 overflow-hidden text-sm">
            {(["growth", "idcw"] as Option[]).map((o) => (
              <Link
                key={o}
                href={urlFor({ option: o })}
                className={`px-3 py-1.5 uppercase ${
                  o === option
                    ? "bg-cyan-900/60 text-cyan-100"
                    : availableOptions.has(o)
                      ? "hover:bg-neutral-900 text-neutral-300"
                      : "text-neutral-700 pointer-events-none"
                }`}
              >
                {o}
              </Link>
            ))}
          </div>
          {currentVariant?.latest_nav != null && (
            <div className="text-sm text-neutral-400">
              Latest NAV: <span className="text-neutral-100 font-medium">{formatNav(currentVariant.latest_nav)}</span>{" "}
              as of {formatDate(currentVariant.latest_nav_date)}
            </div>
          )}
        </div>

        {variantError ? (
          <div className="rounded-lg border border-amber-900 bg-amber-950/40 p-6 text-sm text-amber-200">
            {variantError} Try{" "}
            <Link href={`/research/${fundId}`} className="underline">
              the direct/growth variant
            </Link>
            .
          </div>
        ) : (
          <>
            <section>
              <h2 className="text-sm uppercase tracking-wide text-neutral-500 mb-3">Returns (Annualized)</h2>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                {Object.entries(returns!.windows).map(([key, w]) => (
                  <StatCard
                    key={key}
                    label={RETURN_WINDOW_LABELS[key] ?? key}
                    value={w.available ? formatPct(w.cagr_pct) : "N/A"}
                    valueClassName={w.available ? signColorClass(w.cagr_pct) : "text-neutral-600"}
                    hint={w.available ? undefined : "Not enough NAV history yet"}
                  />
                ))}
              </div>
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-neutral-500 mb-3">Performance vs Benchmark</h2>
              <div className="rounded-lg border border-neutral-800 p-4">
                <NavChart
                  fundPoints={navHistory!.fund_points}
                  benchmarkPoints={navHistory!.benchmark_points}
                  fundLabel={fund.scheme_name}
                  benchmarkLabel={navHistory!.benchmark_name}
                />
              </div>
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-neutral-500 mb-3">
                Risk &amp; Survival
                <span className="text-neutral-600 normal-case tracking-normal ml-2">
                  (assumes {formatNumber(risk!.risk_free_rate_pct)}% annual risk-free rate)
                </span>
              </h2>
              {risk!.available ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <StatCard label="Volatility" value={`${formatNumber(risk!.volatility_pct)}%`} />
                  <StatCard label="Downside Deviation" value={`${formatNumber(risk!.downside_deviation_pct)}%`} />
                  <StatCard
                    label="Sharpe Ratio"
                    value={formatNumber(risk!.sharpe_ratio)}
                    valueClassName={signColorClass(risk!.sharpe_ratio)}
                  />
                  <StatCard
                    label="Sortino Ratio"
                    value={formatNumber(risk!.sortino_ratio)}
                    valueClassName={signColorClass(risk!.sortino_ratio)}
                  />
                  <StatCard
                    label="Upside Capture"
                    value={risk!.upside_capture_pct !== null ? `${formatNumber(risk!.upside_capture_pct, 1)}%` : "N/A"}
                  />
                  <StatCard
                    label="Downside Capture"
                    value={risk!.downside_capture_pct !== null ? `${formatNumber(risk!.downside_capture_pct, 1)}%` : "N/A"}
                  />
                  <StatCard label="Beta" value={formatNumber(risk!.beta)} />
                  <StatCard
                    label="Jensen's Alpha"
                    value={risk!.jensen_alpha_pct !== null ? formatPct(risk!.jensen_alpha_pct) : "N/A"}
                    valueClassName={signColorClass(risk!.jensen_alpha_pct)}
                  />
                </div>
              ) : (
                <p className="text-sm text-neutral-500">Not enough NAV history to compute risk metrics yet.</p>
              )}
            </section>

            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm uppercase tracking-wide text-neutral-500">Rolling Returns</h2>
                <div className="flex rounded-md border border-neutral-800 overflow-hidden text-xs">
                  {ROLLING_WINDOW_OPTIONS.map((w) => (
                    <Link
                      key={w}
                      href={urlFor({ window: w })}
                      className={`px-3 py-1 ${
                        w === windowYears ? "bg-cyan-900/60 text-cyan-100" : "hover:bg-neutral-900 text-neutral-400"
                      }`}
                    >
                      {w}Y
                    </Link>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-neutral-800 p-4 space-y-4">
                {rolling!.available ? (
                  <>
                    <DistributionBar distribution={rolling!.distribution} />
                    {rolling!.benchmark_consistency && (
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-neutral-900">
                        <StatCard
                          label="Beat Benchmark"
                          value={formatNumber(rolling!.benchmark_consistency.beat_rate_pct, 1) + "%"}
                          hint={`of ${rolling!.benchmark_consistency.aligned_windows} rolling windows`}
                        />
                        <StatCard
                          label="Avg Excess Return"
                          value={formatPct(rolling!.benchmark_consistency.avg_excess_return)}
                          valueClassName={signColorClass(rolling!.benchmark_consistency.avg_excess_return)}
                        />
                        <StatCard
                          label="Median Excess Return"
                          value={formatPct(rolling!.benchmark_consistency.median_excess_return)}
                          valueClassName={signColorClass(rolling!.benchmark_consistency.median_excess_return)}
                        />
                        <StatCard
                          label="Worst Relative Window"
                          value={formatPct(rolling!.benchmark_consistency.worst_relative_return)}
                          valueClassName={signColorClass(rolling!.benchmark_consistency.worst_relative_return)}
                        />
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-neutral-500">
                    Not enough NAV history for a {windowYears}-year rolling window yet.
                  </p>
                )}
              </div>
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-neutral-500 mb-3">Drawdown</h2>
              {drawdown!.available ? (
                <div className="rounded-lg border border-neutral-800 p-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <StatCard
                    label="Max Drawdown"
                    value={formatPct(drawdown!.max_drawdown_pct)}
                    valueClassName="text-rose-400"
                  />
                  <StatCard label="Peak" value={formatDate(drawdown!.peak_date)} hint={formatNav(drawdown!.peak_nav)} />
                  <StatCard
                    label="Trough"
                    value={formatDate(drawdown!.trough_date)}
                    hint={formatNav(drawdown!.trough_nav)}
                  />
                  <StatCard
                    label="Recovery"
                    value={drawdown!.recovered ? formatDate(drawdown!.recovery_date) : "Not yet recovered"}
                    hint={
                      drawdown!.recovery_duration_days != null
                        ? `${drawdown!.recovery_duration_days} days from trough`
                        : undefined
                    }
                    valueClassName={drawdown!.recovered ? "" : "text-amber-400"}
                  />
                </div>
              ) : (
                <p className="text-sm text-neutral-500">Not enough NAV history to compute drawdown yet.</p>
              )}
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-neutral-500 mb-1">Market-Cycle Behaviour</h2>
              <p className="text-xs text-neutral-600 mb-3">{marketRegimes!.methodology_note}</p>
              {marketRegimes!.regimes.length > 0 ? (
                <>
                  <p className="text-sm text-neutral-400 mb-3">
                    Beat its benchmark in {marketRegimes!.regimes_outperformed} of{" "}
                    {marketRegimes!.regimes_with_comparison} comparable periods.
                  </p>
                  <MarketRegimeTable regimes={marketRegimes!.regimes} />
                </>
              ) : (
                <p className="text-sm text-neutral-500">No market regimes defined yet.</p>
              )}
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-neutral-500 mb-1">Stress Test</h2>
              <p className="text-xs text-neutral-600 mb-3">{stressTest!.hypothetical_notice}</p>
              <StressTestPanel scenarios={stressTest!.scenarios} />
            </section>
          </>
        )}

        <section>
          <h2 className="text-sm uppercase tracking-wide text-neutral-500 mb-3">Portfolio DNA &amp; Concentration</h2>
          {portfolio.available ? (
            <div className="space-y-4">
              <p className="text-xs text-neutral-500">
                Holdings as of {formatDate(portfolio.as_of_date)} · Source: {portfolio.source_name ?? "unknown"}
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard label="Holdings Disclosed" value={String(portfolio.total_holdings)} />
                <StatCard
                  label="Top 5 Weight"
                  value={portfolio.top5_weight_pct !== null ? `${formatNumber(portfolio.top5_weight_pct, 1)}%` : "—"}
                />
                <StatCard
                  label="Top 10 Weight"
                  value={portfolio.top10_weight_pct !== null ? `${formatNumber(portfolio.top10_weight_pct, 1)}%` : "—"}
                />
                <StatCard
                  label="HHI Concentration"
                  value={portfolio.hhi !== null ? formatNumber(portfolio.hhi, 0) : "—"}
                  hint={portfolio.hhi_label ? HHI_LABELS[portfolio.hhi_label] ?? portfolio.hhi_label : undefined}
                  valueClassName={
                    portfolio.hhi_label === "high_concentration"
                      ? "text-rose-400"
                      : portfolio.hhi_label === "moderate_concentration"
                        ? "text-amber-400"
                        : "text-emerald-400"
                  }
                />
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div className="rounded-lg border border-neutral-800 p-4">
                  <h3 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">Sector Allocation</h3>
                  <AllocationBar slices={portfolio.sector_allocation} />
                </div>
                <div className="rounded-lg border border-neutral-800 p-4">
                  <h3 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">Market-Cap Allocation</h3>
                  <AllocationBar slices={portfolio.market_cap_allocation} />
                </div>
              </div>

              <div>
                <h3 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">Top Holdings</h3>
                <HoldingsTable holdings={portfolio.top_holdings} />
              </div>
              <p className="text-xs text-neutral-500">
                Weights shown are of disclosed holdings only ({formatNumber(portfolio.total_disclosed_weight_pct, 1)}%
                of the portfolio) — remaining exposure (cash, undisclosed holdings) is not shown.
              </p>
            </div>
          ) : (
            <p className="text-sm text-neutral-500">No portfolio holdings data available for this fund yet.</p>
          )}
        </section>

        <p className="text-xs text-neutral-600 border-t border-neutral-900 pt-4">
          {(returns ?? risk ?? rolling ?? drawdown ?? portfolio)?.disclaimer ??
            "Historical performance does not guarantee future results."}
        </p>
      </main>
    </div>
  );
}
