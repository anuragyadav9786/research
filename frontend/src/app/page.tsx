import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { AnimatedHeroHeadline } from "@/components/hero/AnimatedHeroHeadline";
import { RealityCheckWidget, type RealityCheckFund } from "@/components/fund/RealityCheckWidget";
import { BenchmarkDeltaBadge, type BenchmarkMetrics, deltaVsBenchmark, safetyMarginVsBenchmark } from "@/components/fund/BenchmarkDeltaBadge";
import { countFunds, getFund, getFundDrawdown, getFundReturns, getFundRollingReturns, listFunds } from "@/lib/api";
import { formatNav, signColorClass } from "@/lib/format";
import type { FundDetail, VariantSummary } from "@/types/fund";

// A small, fixed-size sample rather than any kind of "top performers"
// ranking — this platform has no popularity/AUM data to honestly back a
// "top funds" claim. These three are real funds deliberately backfilled
// with their full real NAV history (see the backfill_featured_funds
// workflow step) so this page can show genuine multi-year numbers instead
// of the "not enough history yet" every other fund still shows — real
// AMFI ingestion for this platform only started a couple of days ago.
const FEATURED_FUND_IDS = [1833, 2236, 2140] as const; // Parag Parikh Flexi Cap, Mirae Asset Large Cap, Quant Small Cap
const REALITY_CHECK_PAIR = [1833, 2236] as const; // Parag Parikh Flexi Cap vs Mirae Asset Large Cap

// A real, currently-onboarded passive index fund, standing in for a
// "vs Benchmark" comparison — see BenchmarkDeltaBadge.tsx for why an
// index fund (not a raw price index, which this platform has no real
// history for at all) is the honest choice here.
const BENCHMARK_FUND_ID = 2893; // Axis Nifty 50 Index Fund
const BENCHMARK_LABEL = "Nifty 50 Index";

const EXPLORE_COUNT = 6;

// Substrings of real AMFI-style category text (e.g. "Equity Scheme -
// Large Cap Fund", "Equity Schemes - Large Cap Fund" — AMCs don't agree
// on "Scheme" vs "Schemes"), matched via /research's category filter
// (a case-insensitive substring match, not exact — see
// fund_repository.py) so a single fixed label like "Large Cap" still
// works across every AMC's own wording.
const CATEGORY_CHIPS = ["Large Cap", "Flexi Cap", "Mid Cap", "Small Cap", "Debt"];

const FEATURES = [
  {
    href: "/research",
    title: "Single-Fund Stress Test",
    description: "Analyze rolling returns, drawdown recovery days, and capture ratios computed from raw NAV history.",
    icon: PulseIcon,
  },
  {
    href: "/research/compare",
    title: "Head-to-Head Benchmark",
    description: "Place two funds side by side to expose where their performance divergence actually occurred.",
    icon: SplitIcon,
  },
  {
    href: "/portfolio",
    title: "Blended Portfolio Risk",
    description: "Combine your holdings to calculate real aggregate asset allocation, overlap, and blended drawdown.",
    icon: LayersIcon,
  },
  {
    href: "/market",
    title: "Market Cycle Intelligence",
    description: "Examine how funds behaved during the 2020 crash, 2021 bull run, and 2022-2023 rate cycle.",
    icon: WaveIcon,
  },
];

function directGrowthVariant(fund: FundDetail): VariantSummary | undefined {
  return fund.variants.find((v) => v.plan === "direct" && v.option === "growth") ?? fund.variants[0];
}

async function loadBenchmarkMetrics(): Promise<BenchmarkMetrics | null> {
  try {
    const [returns, rolling, drawdown] = await Promise.all([
      getFundReturns(BENCHMARK_FUND_ID),
      getFundRollingReturns(BENCHMARK_FUND_ID, { window_years: 3 }),
      getFundDrawdown(BENCHMARK_FUND_ID),
    ]);
    return {
      name: BENCHMARK_LABEL,
      cagr3y: returns.windows["3y"]?.available ? returns.windows["3y"].cagr_pct : null,
      medianRolling3y: rolling.available ? rolling.distribution.median : null,
      maxDrawdown: drawdown.available ? drawdown.max_drawdown_pct : null,
    };
  } catch {
    return null;
  }
}

async function loadRealityCheckFund(fundId: number): Promise<RealityCheckFund | null> {
  try {
    const [fund, returns, rolling, drawdown] = await Promise.all([
      getFund(fundId),
      getFundReturns(fundId),
      getFundRollingReturns(fundId, { window_years: 3 }),
      getFundDrawdown(fundId),
    ]);
    return {
      id: fundId,
      name: fund.scheme_name,
      category: fund.category,
      cagr3y: returns.windows["3y"]?.available ? returns.windows["3y"].cagr_pct : null,
      medianRolling3y: rolling.available ? rolling.distribution.median : null,
      maxDrawdown: drawdown.available ? drawdown.max_drawdown_pct : null,
      distribution: rolling.distribution,
    };
  } catch {
    return null;
  }
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;
  const activeTab = tab === "all" ? "all" : "complete";

  const [fundCount, realityA, realityB, benchmark, exploreList] = await Promise.all([
    countFunds().catch(() => ({ count: 0 })),
    loadRealityCheckFund(REALITY_CHECK_PAIR[0]),
    loadRealityCheckFund(REALITY_CHECK_PAIR[1]),
    loadBenchmarkMetrics(),
    activeTab === "all" ? listFunds({ limit: EXPLORE_COUNT }).catch(() => ({ items: [], has_more: false })) : null,
  ]);

  // Fetched unconditionally (unlike featuredFunds below) so the hero's fund
  // cards stay populated regardless of which Explore Funds tab is active.
  const heroFunds = (await Promise.all(FEATURED_FUND_IDS.map((id) => getFund(id).catch(() => null)))).filter(
    (f): f is FundDetail => f !== null,
  );

  const featuredFunds =
    activeTab === "complete"
      ? heroFunds
      : (await Promise.all((exploreList?.items ?? []).map((f) => getFund(f.id).catch(() => null)))).filter(
          (f): f is FundDetail => f !== null,
        );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="dashboard" />

      <main className="px-8 py-12 max-w-5xl mx-auto space-y-16">
        <section className="relative isolate flex flex-col items-center text-center py-6 sm:py-10">
          {/* Soft radial glow — purely decorative, sits behind the search bar like a focal spotlight. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 -z-10 flex items-start justify-center"
          >
            <div className="mt-8 h-64 w-64 sm:h-80 sm:w-80 rounded-full bg-indigo-600/20 blur-3xl" />
          </div>

          <div className="max-w-2xl">
            <AnimatedHeroHeadline centered />
          </div>

          <form action="/research" className="mt-8 w-full max-w-xl">
            <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900 pl-5 pr-1.5 py-1.5 shadow-lg shadow-indigo-950/40 focus-within:border-indigo-600 transition-colors">
              <input
                type="text"
                name="search"
                placeholder="Search by fund, AMC, or category…"
                className="min-w-0 flex-1 bg-transparent text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none"
              />
              <kbd className="hidden sm:inline-flex items-center rounded border border-slate-700 px-1.5 py-0.5 text-[10px] font-mono text-slate-500">
                Enter ↵
              </kbd>
              <button
                type="submit"
                className="shrink-0 rounded-full bg-indigo-500 text-white font-medium text-sm px-4 py-2 hover:bg-indigo-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
              >
                Search
              </button>
            </div>
          </form>

          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {CATEGORY_CHIPS.map((chip) => (
              <Link
                key={chip}
                href={`/research?category=${encodeURIComponent(chip)}`}
                className="rounded-full border border-slate-800 px-3 py-1 text-xs text-slate-400 hover:border-slate-700 hover:text-slate-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
              >
                {chip}
              </Link>
            ))}
          </div>

          {/* For visitors who don't yet know which fund to search for — a
           * concrete, already-populated example beats an empty search box.
           * Only shown when a real backfilled fund is actually available, so
           * this never links somewhere the fallback state below admits is
           * degraded. */}
          {heroFunds.length > 0 && (
            <Link
              href={`/research/${heroFunds[0].id}`}
              className="mt-5 inline-flex items-center gap-1.5 text-sm text-indigo-400 hover:text-indigo-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 rounded-sm"
            >
              See a live example: {heroFunds[0].scheme_name} →
            </Link>
          )}

          <div className="mt-8 w-full max-w-4xl text-left">
            <CompleteDataGrid fundIds={FEATURED_FUND_IDS} funds={heroFunds} benchmark={benchmark} />
          </div>
        </section>

        {realityA && realityB ? (
          <RealityCheckWidget fundA={realityA} fundB={realityB} benchmark={benchmark} />
        ) : (
          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-6">
            <h2 className="text-lg font-semibold text-slate-100">See What Most Portals Hide</h2>
            <p className="text-sm text-slate-500 mt-2">
              This comparison is temporarily unavailable while its fund data refreshes.{" "}
              <Link href="/research/compare" className="text-indigo-400 hover:text-indigo-300">
                Compare any two funds yourself →
              </Link>
            </p>
          </div>
        )}

        <section className="space-y-4">
          <div className="flex items-baseline justify-between flex-wrap gap-3">
            <h2 className="text-sm uppercase tracking-wide text-slate-500">Explore Funds</h2>
            <div className="flex rounded-md border border-slate-800 overflow-hidden text-xs">
              <Link
                href="/?tab=complete"
                className={`px-3 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-500 ${
                  activeTab === "complete" ? "bg-indigo-900/50 text-indigo-200" : "text-slate-400 hover:bg-slate-900"
                }`}
              >
                Most Complete Data
              </Link>
              <Link
                href="/?tab=all"
                className={`px-3 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-500 ${
                  activeTab === "all" ? "bg-indigo-900/50 text-indigo-200" : "text-slate-400 hover:bg-slate-900"
                }`}
              >
                All Funds
              </Link>
            </div>
          </div>

          {activeTab === "complete" ? (
            <CompleteDataGrid fundIds={FEATURED_FUND_IDS} funds={featuredFunds} benchmark={benchmark} />
          ) : (
            <AllFundsGrid funds={featuredFunds} />
          )}

          <Link
            href="/research"
            className="inline-block rounded-sm text-xs text-indigo-400 hover:text-indigo-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
          >
            Browse all {fundCount.count.toLocaleString("en-IN")} funds →
          </Link>
        </section>

        <section className="space-y-4">
          <h2 className="text-sm uppercase tracking-wide text-slate-500">What You Can Do</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {FEATURES.map((feature) => (
              <Link key={feature.href} href={feature.href} className={`${CARD_LINK_CLASS} p-6 space-y-3`}>
                <feature.icon className="h-5 w-5 text-indigo-400" />
                <div>
                  <h3 className="text-sm font-semibold text-slate-100">{feature.title}</h3>
                  <p className="text-sm text-slate-500 mt-1">{feature.description}</p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

const CARD_LINK_CLASS =
  "rounded-lg border border-slate-800 hover:border-slate-700 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-indigo-950/40 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950";

async function CompleteDataGrid({
  fundIds,
  funds,
  benchmark,
}: {
  fundIds: readonly number[];
  funds: FundDetail[];
  benchmark?: BenchmarkMetrics | null;
}) {
  const metrics = await Promise.all(
    fundIds.map(async (id) => {
      const [returns, drawdown] = await Promise.all([
        getFundReturns(id).catch(() => null),
        getFundDrawdown(id).catch(() => null),
      ]);
      return {
        id,
        cagr3y: returns?.windows["3y"]?.available ? returns.windows["3y"].cagr_pct : null,
        maxDrawdown: drawdown?.available ? drawdown.max_drawdown_pct : null,
      };
    }),
  );

  const availableIds = fundIds.filter((id) => funds.some((f) => f.id === id));
  if (availableIds.length === 0) {
    return (
      <p className="text-sm text-slate-500 py-6">
        Featured funds are refreshing —{" "}
        <Link href="/research" className="text-indigo-400 hover:text-indigo-300">
          browse all funds →
        </Link>
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {fundIds.map((id) => {
        const fund = funds.find((f) => f.id === id);
        const m = metrics.find((x) => x.id === id);
        if (!fund) return null;
        return (
          <Link key={id} href={`/research/${id}`} className={`${CARD_LINK_CLASS} p-4 space-y-3`}>
            <div>
              <p className="text-sm font-medium leading-snug text-slate-100 line-clamp-2">{fund.scheme_name}</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {fund.amc_name} · {fund.category}
              </p>
            </div>
            <div className="flex items-start justify-between pt-2 border-t border-slate-900 text-xs">
              <div>
                <div className="text-slate-500">3Y CAGR</div>
                <div className={`font-mono tabular-nums mt-0.5 ${m?.cagr3y != null ? signColorClass(m.cagr3y) : "text-slate-600"}`}>
                  {m?.cagr3y != null ? `${m.cagr3y.toFixed(1)}%` : "—"}
                </div>
                {benchmark && (
                  <BenchmarkDeltaBadge
                    className="mt-1"
                    delta={deltaVsBenchmark(m?.cagr3y ?? null, benchmark.cagr3y)}
                    kind="return"
                    benchmarkName={benchmark.name}
                  />
                )}
              </div>
              <div className="text-right">
                <div className="text-slate-500">Max Drawdown</div>
                <div className="font-mono tabular-nums text-rose-400 mt-0.5">
                  {m?.maxDrawdown != null ? `${m.maxDrawdown.toFixed(1)}%` : "—"}
                </div>
                {benchmark && (
                  <BenchmarkDeltaBadge
                    className="mt-1 justify-end"
                    delta={safetyMarginVsBenchmark(m?.maxDrawdown ?? null, benchmark.maxDrawdown)}
                    kind="drawdown"
                    benchmarkName={benchmark.name}
                  />
                )}
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

function AllFundsGrid({ funds }: { funds: FundDetail[] }) {
  if (funds.length === 0) return <p className="text-sm text-slate-500">No funds available yet.</p>;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {funds.map((fund) => {
        const variant = directGrowthVariant(fund);
        return (
          <Link key={fund.id} href={`/research/${fund.id}`} className={`${CARD_LINK_CLASS} p-4 space-y-2`}>
            <div>
              <p className="text-sm font-medium leading-snug text-slate-100 line-clamp-2">{fund.scheme_name}</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {fund.amc_name} · {fund.category}
              </p>
            </div>
            <div className="flex items-baseline justify-between pt-1 border-t border-slate-900">
              <span className="text-xs text-slate-500">Latest NAV</span>
              <span className="text-sm font-mono tabular-nums text-slate-100">
                {variant?.latest_nav != null ? formatNav(variant.latest_nav) : "—"}
              </span>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

function PulseIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className={className}>
      <path d="M3 12h4l2-7 4 14 2-7h6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SplitIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className={className}>
      <path d="M12 3v18M7 7l-4 5 4 5M17 7l4 5-4 5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function LayersIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className={className}>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="m3 13 9 5 9-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function WaveIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className={className}>
      <path d="M3 17c2-4 4-4 6 0s4 4 6 0 4-4 6 0" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3 9c2-4 4-4 6 0s4 4 6 0 4-4 6 0" strokeLinecap="round" strokeLinejoin="round" opacity="0.4" />
    </svg>
  );
}
