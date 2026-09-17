import Link from "next/link";
import { notFound } from "next/navigation";

import { SiteHeader } from "@/components/layout/SiteHeader";
import {
  ApiError,
  getFund,
  getFundIntelligence,
  getFundMarketRegimes,
  getFundNavHistory,
  getFundPortfolio,
  getFundRollingReturns,
  getFundStressTest,
} from "@/lib/api";
import { formatDate, formatNav, formatNumber, formatPct, signColorClass } from "@/lib/format";
import { AllocationBar } from "@/components/fund/AllocationBar";
import { Disclosure } from "@/components/fund/Disclosure";
import { DistributionBar } from "@/components/fund/DistributionBar";
import { HoldingsTable } from "@/components/fund/HoldingsTable";
import { MarketRegimeTable } from "@/components/fund/MarketRegimeTable";
import { MetricDisclosure } from "@/components/fund/MetricDisclosure";
import { NavChart } from "@/components/fund/NavChart";
import { RollingReturnBarChart } from "@/components/fund/RollingReturnBarChart";
import { ScalarScaleBar } from "@/components/fund/ScalarScaleBar";
import { StatCard } from "@/components/fund/StatCard";
import { AiSummaryPanel } from "@/components/fund/AiSummaryPanel";
import { StressTestPanel } from "@/components/fund/StressTestPanel";
import {
  interpretBeta,
  interpretDownsideCapture,
  interpretDownsideDeviation,
  interpretJensenAlpha,
  interpretMaxDrawdown,
  interpretRollingReturns,
  interpretSharpe,
  interpretSortino,
  interpretUpsideCapture,
  interpretVolatility,
} from "@/lib/metricInterpretation";
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

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950";

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
    // getFundNavHistory goes first and is awaited alone, not folded into
    // the Promise.all below. Every one of these endpoints resolves the
    // same variant server-side and triggers ensure_nav_history's one-time
    // mfapi.in backfill on a brand-new fund (see lazy_nav_backfill.py) —
    // firing everything at once would let each independently race to
    // start that same fetch before any has committed the "done" flag.
    // Awaiting one first means it's already committed by the time the
    // rest run, so they see it and skip straight to a fast local read.
    navHistory = await getFundNavHistory(fundId, variantParams);

    // getFundIntelligence bundles returns + risk + rolling(3y) + drawdown
    // into one backend call instead of four separate ones. It only
    // computes the 3-year rolling case, so a non-default window still
    // needs its own request — done in the same Promise.all as the two
    // endpoints /intelligence doesn't cover at all.
    const intelligence = await getFundIntelligence(fundId, variantParams);
    returns = intelligence.returns;
    risk = intelligence.risk;
    drawdown = intelligence.drawdown;

    [rolling, marketRegimes, stressTest] = await Promise.all([
      windowYears === 3 ? Promise.resolve(intelligence.rolling_3y) : getFundRollingReturns(fundId, { ...variantParams, window_years: windowYears }),
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
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="research" />

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-8">
        <div className="flex items-start justify-between">
          <div>
            <Link
              href="/research"
              className={`text-sm text-slate-500 hover:text-slate-300 rounded-sm ${FOCUS_RING}`}
            >
              ← Back to Research
            </Link>
            <h1 className="text-2xl font-semibold mt-2">{fund.scheme_name}</h1>
            <p className="text-slate-400 text-sm mt-1">
              {fund.amc_name} · {fund.category}
              {fund.benchmark_name && <> · Benchmark: {fund.benchmark_name}</>}
            </p>
          </div>
          <Link
            href={`/research/compare?a=${fundId}`}
            className={`text-sm rounded-md border border-slate-800 px-3 py-1.5 text-slate-400 hover:text-slate-100 hover:border-slate-700 whitespace-nowrap ${FOCUS_RING}`}
          >
            Compare with…
          </Link>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <div className="flex rounded-md border border-slate-800 overflow-hidden text-sm">
            {(["direct", "regular"] as Plan[]).map((p) => (
              <Link
                key={p}
                href={urlFor({ plan: p })}
                aria-disabled={!availablePlans.has(p)}
                className={`px-3 py-1.5 capitalize ${FOCUS_RING} ${
                  p === plan
                    ? "bg-indigo-900/60 text-indigo-800"
                    : availablePlans.has(p)
                      ? "hover:bg-slate-900 text-slate-300"
                      : "text-slate-700 pointer-events-none"
                }`}
              >
                {p}
              </Link>
            ))}
          </div>
          <div className="flex rounded-md border border-slate-800 overflow-hidden text-sm">
            {(["growth", "idcw"] as Option[]).map((o) => (
              <Link
                key={o}
                href={urlFor({ option: o })}
                className={`px-3 py-1.5 uppercase ${FOCUS_RING} ${
                  o === option
                    ? "bg-indigo-900/60 text-indigo-800"
                    : availableOptions.has(o)
                      ? "hover:bg-slate-900 text-slate-300"
                      : "text-slate-700 pointer-events-none"
                }`}
              >
                {o}
              </Link>
            ))}
          </div>
          {currentVariant?.latest_nav != null && (
            <div className="text-sm text-slate-400">
              Latest NAV: <span className="text-slate-100 font-medium">{formatNav(currentVariant.latest_nav)}</span>{" "}
              as of {formatDate(currentVariant.latest_nav_date)}
            </div>
          )}
        </div>

        {variantError ? (
          <div className="rounded-lg border border-amber-900 bg-amber-950/40 p-6 text-sm text-amber-200">
            {variantError} Try{" "}
            <Link href={`/research/${fundId}`} className={`underline rounded-sm ${FOCUS_RING}`}>
              the direct/growth variant
            </Link>
            .
          </div>
        ) : (
          <>
            <section>
              <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-1">Returns (Annualized)</h2>
              <p className="text-xs text-slate-500 mb-3">
                Point-to-point figures — each depends on the exact day measured. See Rolling Returns below for how
                consistent this fund&rsquo;s outcomes actually were.
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                {Object.entries(returns!.windows).map(([key, w]) => (
                  <StatCard
                    key={key}
                    label={RETURN_WINDOW_LABELS[key] ?? key}
                    value={w.available ? formatPct(w.cagr_pct) : "N/A"}
                    valueClassName={w.available ? signColorClass(w.cagr_pct) : "text-slate-600"}
                    hint={w.available ? undefined : "Not enough NAV history yet"}
                  />
                ))}
              </div>
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Performance vs Benchmark</h2>
              <div className="rounded-lg border border-slate-800 p-4">
                <NavChart
                  fundPoints={navHistory!.fund_points}
                  benchmarkPoints={navHistory!.benchmark_points}
                  fundLabel={fund.scheme_name}
                  benchmarkLabel={navHistory!.benchmark_name}
                />
              </div>
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">
                Risk &amp; Survival
                <span className="text-slate-600 normal-case tracking-normal ml-2">
                  (assumes {formatNumber(risk!.risk_free_rate_pct)}% annual risk-free rate)
                </span>
              </h2>
              {risk!.available ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {(() => {
                    const cards: {
                      key: string;
                      label: string;
                      raw: number | null;
                      interp: ReturnType<typeof interpretSharpe>;
                      formatValue: (v: number) => string;
                      displayValue: string;
                      preciseValue: string;
                      usesRiskFreeRate: boolean;
                    }[] = [
                      {
                        key: "sharpe",
                        label: "Sharpe Ratio",
                        raw: risk!.sharpe_ratio,
                        interp: interpretSharpe(risk!.sharpe_ratio),
                        formatValue: (v) => formatNumber(v),
                        displayValue: formatNumber(risk!.sharpe_ratio),
                        preciseValue: formatNumber(risk!.sharpe_ratio, 4),
                        usesRiskFreeRate: true,
                      },
                      {
                        key: "sortino",
                        label: "Sortino Ratio",
                        raw: risk!.sortino_ratio,
                        interp: interpretSortino(risk!.sortino_ratio),
                        formatValue: (v) => formatNumber(v),
                        displayValue: formatNumber(risk!.sortino_ratio),
                        preciseValue: formatNumber(risk!.sortino_ratio, 4),
                        usesRiskFreeRate: true,
                      },
                      {
                        key: "volatility",
                        label: "Volatility",
                        raw: risk!.volatility_pct,
                        interp: interpretVolatility(risk!.volatility_pct),
                        formatValue: (v) => `${formatNumber(v, 0)}%`,
                        displayValue: `${formatNumber(risk!.volatility_pct)}%`,
                        preciseValue: `${formatNumber(risk!.volatility_pct, 4)}%`,
                        usesRiskFreeRate: false,
                      },
                      {
                        key: "downside_deviation",
                        label: "Downside Deviation",
                        raw: risk!.downside_deviation_pct,
                        interp: interpretDownsideDeviation(risk!.downside_deviation_pct),
                        formatValue: (v) => `${formatNumber(v, 0)}%`,
                        displayValue: `${formatNumber(risk!.downside_deviation_pct)}%`,
                        preciseValue: `${formatNumber(risk!.downside_deviation_pct, 4)}%`,
                        usesRiskFreeRate: false,
                      },
                      {
                        key: "upside_capture",
                        label: "Upside Capture",
                        raw: risk!.upside_capture_pct,
                        interp: interpretUpsideCapture(risk!.upside_capture_pct),
                        formatValue: (v) => `${formatNumber(v, 0)}%`,
                        displayValue: risk!.upside_capture_pct !== null ? `${formatNumber(risk!.upside_capture_pct, 1)}%` : "N/A",
                        preciseValue: `${formatNumber(risk!.upside_capture_pct, 4)}%`,
                        usesRiskFreeRate: false,
                      },
                      {
                        key: "downside_capture",
                        label: "Downside Capture",
                        raw: risk!.downside_capture_pct,
                        interp: interpretDownsideCapture(risk!.downside_capture_pct),
                        formatValue: (v) => `${formatNumber(v, 0)}%`,
                        displayValue: risk!.downside_capture_pct !== null ? `${formatNumber(risk!.downside_capture_pct, 1)}%` : "N/A",
                        preciseValue: `${formatNumber(risk!.downside_capture_pct, 4)}%`,
                        usesRiskFreeRate: false,
                      },
                      {
                        key: "beta",
                        label: "Beta",
                        raw: risk!.beta,
                        interp: interpretBeta(risk!.beta),
                        formatValue: (v) => formatNumber(v, 1),
                        displayValue: formatNumber(risk!.beta),
                        preciseValue: formatNumber(risk!.beta, 4),
                        usesRiskFreeRate: false,
                      },
                      {
                        key: "alpha",
                        label: "Jensen's Alpha",
                        raw: risk!.jensen_alpha_pct,
                        interp: interpretJensenAlpha(risk!.jensen_alpha_pct),
                        formatValue: (v) => formatPct(v, 0),
                        displayValue: risk!.jensen_alpha_pct !== null ? formatPct(risk!.jensen_alpha_pct) : "N/A",
                        preciseValue: formatPct(risk!.jensen_alpha_pct, 4),
                        usesRiskFreeRate: true,
                      },
                    ];

                    return cards.map((card) => {
                      if (card.raw === null || card.interp === null) {
                        return <StatCard key={card.key} label={card.label} value="N/A" />;
                      }
                      return (
                        <MetricDisclosure
                          key={card.key}
                          label={card.label}
                          value={card.displayValue}
                          valueClassName={card.interp.verdictColorClass}
                          sentence={card.interp.sentence}
                          tier3={
                            <p className="text-sm font-mono tabular-nums text-slate-200">
                              {card.preciseValue}
                              <span className="text-slate-500 font-sans ml-2">
                                · computed from {risk!.observations_used} monthly return observations
                                {card.usesRiskFreeRate ? ` at a ${formatNumber(risk!.risk_free_rate_pct)}% annual risk-free rate` : ""}
                              </span>
                            </p>
                          }
                          tier2={
                            <ScalarScaleBar
                              value={card.raw}
                              scaleMin={card.interp.scaleMin}
                              scaleMax={card.interp.scaleMax}
                              zones={card.interp.zones}
                              formatValue={card.formatValue}
                            />
                          }
                        />
                      );
                    });
                  })()}
                </div>
              ) : (
                <p className="text-sm text-slate-500">Not enough NAV history to compute risk metrics yet.</p>
              )}
            </section>

            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm uppercase tracking-wide text-slate-500">Rolling Returns</h2>
                <div className="flex rounded-md border border-slate-800 overflow-hidden text-xs">
                  {ROLLING_WINDOW_OPTIONS.map((w) => (
                    <Link
                      key={w}
                      href={urlFor({ window: w })}
                      className={`px-3 py-1 ${FOCUS_RING} ${
                        w === windowYears ? "bg-indigo-900/60 text-indigo-800" : "hover:bg-slate-900 text-slate-400"
                      }`}
                    >
                      {w}Y
                    </Link>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 p-4 space-y-4">
                {rolling!.available ? (
                  <>
                    <p className="text-sm text-slate-300">
                      {interpretRollingReturns(
                        rolling!.distribution,
                        windowYears,
                        rolling!.benchmark_consistency?.beat_rate_pct ?? null,
                      )}
                    </p>
                    <DistributionBar distribution={rolling!.distribution} />
                    <Disclosure label="Show exact percentile values">
                      <dl className="grid grid-cols-3 sm:grid-cols-5 gap-3 text-center">
                        {(
                          [
                            ["P10", rolling!.distribution.p10],
                            ["P25", rolling!.distribution.p25],
                            ["Median", rolling!.distribution.median],
                            ["P75", rolling!.distribution.p75],
                            ["P90", rolling!.distribution.p90],
                          ] as const
                        ).map(([label, v]) => (
                          <div key={label}>
                            <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
                            <dd className="text-sm font-mono tabular-nums text-slate-200 mt-0.5">{formatPct(v)}</dd>
                          </div>
                        ))}
                      </dl>
                    </Disclosure>
                    {rolling!.benchmark_consistency && (
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-slate-900">
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
                  <p className="text-sm text-slate-500">
                    Not enough NAV history for a {windowYears}-year rolling window yet.
                  </p>
                )}
                <div className="pt-4 border-t border-slate-900">
                  <RollingReturnBarChart fundId={fundId} plan={plan} option={option} />
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Drawdown</h2>
              {drawdown!.available ? (
                <div className="space-y-3">
                  {(() => {
                    const interp = interpretMaxDrawdown(drawdown!.max_drawdown_pct);
                    return interp === null ? null : (
                      <MetricDisclosure
                        label="Max Drawdown"
                        value={formatPct(drawdown!.max_drawdown_pct)}
                        valueClassName={interp.verdictColorClass}
                        sentence={interp.sentence}
                        tier2={
                          <ScalarScaleBar
                            value={drawdown!.max_drawdown_pct!}
                            scaleMin={interp.scaleMin}
                            scaleMax={interp.scaleMax}
                            zones={interp.zones}
                            formatValue={(v) => formatPct(v, 0)}
                          />
                        }
                      />
                    );
                  })()}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
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
                </div>
              ) : (
                <p className="text-sm text-slate-500">Not enough NAV history to compute drawdown yet.</p>
              )}
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-1">Market-Cycle Behaviour</h2>
              <p className="text-xs text-slate-600 mb-3">{marketRegimes!.methodology_note}</p>
              {marketRegimes!.regimes.length > 0 ? (
                <>
                  <p className="text-sm text-slate-400 mb-3">
                    Beat its benchmark in {marketRegimes!.regimes_outperformed} of{" "}
                    {marketRegimes!.regimes_with_comparison} comparable periods.
                  </p>
                  <MarketRegimeTable regimes={marketRegimes!.regimes} />
                </>
              ) : (
                <p className="text-sm text-slate-500">No market regimes defined yet.</p>
              )}
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-1">Stress Test</h2>
              <p className="text-xs text-slate-600 mb-3">{stressTest!.hypothetical_notice}</p>
              <StressTestPanel scenarios={stressTest!.scenarios} />
            </section>

            <section>
              <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">ThinkFin AI Summary</h2>
              <AiSummaryPanel fundId={fundId} plan={plan} option={option} />
            </section>
          </>
        )}

        <section>
          <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Portfolio DNA &amp; Concentration</h2>
          {portfolio.available ? (
            <div className="space-y-4">
              <p className="text-xs text-slate-500">
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
                <div className="rounded-lg border border-slate-800 p-4">
                  <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Sector Allocation</h3>
                  <AllocationBar slices={portfolio.sector_allocation} />
                </div>
                <div className="rounded-lg border border-slate-800 p-4">
                  <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Market-Cap Allocation</h3>
                  <AllocationBar slices={portfolio.market_cap_allocation} />
                </div>
              </div>

              <div>
                <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Top Holdings</h3>
                <HoldingsTable holdings={portfolio.top_holdings} />
              </div>
              <p className="text-xs text-slate-500">
                Weights shown are of disclosed holdings only ({formatNumber(portfolio.total_disclosed_weight_pct, 1)}%
                of the portfolio) — remaining exposure (cash, undisclosed holdings) is not shown.
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-500">No portfolio holdings data available for this fund yet.</p>
          )}
        </section>

        <p className="text-xs text-slate-600 border-t border-slate-900 pt-4">
          {(returns ?? risk ?? rolling ?? drawdown ?? portfolio)?.disclaimer ??
            "Historical performance does not guarantee future results."}
        </p>
      </main>
    </div>
  );
}
