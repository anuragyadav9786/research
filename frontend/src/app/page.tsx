import Link from "next/link";
import { Suspense } from "react";
import { Activity, GitCompare, Layers, Waves } from "lucide-react";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { MythVsRealityCard, type MythVsRealityData } from "@/components/hero/MythVsRealityCard";
import { PersonaCards } from "@/components/hero/PersonaCards";
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

// The hero's "Myth vs. Reality" anchor is built around one real fund —
// same one as the hero cards' first entry, deliberately backfilled with
// full real NAV history (see the backfill_featured_funds workflow step).
const MYTH_VS_REALITY_FUND_ID = FEATURED_FUND_IDS[0];

// A real, currently-onboarded passive index fund, standing in for a
// "vs Benchmark" comparison — see BenchmarkDeltaBadge.tsx for why an
// index fund (not a raw price index, which this platform has no real
// history for at all) is the honest choice here.
const BENCHMARK_FUND_ID = 2893; // Axis Nifty 50 Index Fund
const BENCHMARK_LABEL = "Nifty 50 Index";

const EXPLORE_COUNT = 6;

const FEATURES = [
  {
    href: "/research",
    title: "Single-Fund Stress Test",
    description: "Analyze rolling returns, drawdown recovery days, and capture ratios computed from raw NAV history.",
    icon: Activity,
  },
  {
    href: "/research/compare",
    title: "Head-to-Head Benchmark",
    description: "Place two funds side by side to expose where their performance divergence actually occurred.",
    icon: GitCompare,
  },
  {
    href: "/portfolio",
    title: "Blended Portfolio Risk",
    description: "Combine your holdings to calculate real aggregate asset allocation, overlap, and blended drawdown.",
    icon: Layers,
  },
  {
    href: "/market",
    title: "Market Cycle Intelligence",
    description: "Examine how funds behaved during the 2020 crash, 2021 bull run, and 2022-2023 rate cycle.",
    icon: Waves,
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

async function loadMythVsRealityData(fundId: number): Promise<MythVsRealityData | null> {
  try {
    const [fund, returns, rolling, drawdown] = await Promise.all([
      getFund(fundId),
      getFundReturns(fundId),
      getFundRollingReturns(fundId, { window_years: 3 }),
      getFundDrawdown(fundId),
    ]);
    if (!rolling.available) return null;
    return {
      id: fundId,
      schemeName: fund.scheme_name,
      category: fund.category,
      cagr3y: returns.windows["3y"]?.available ? returns.windows["3y"].cagr_pct : null,
      maxDrawdown: drawdown.available ? drawdown.max_drawdown_pct : null,
      recovered: drawdown.available ? drawdown.recovered : null,
      recoveryDurationDays: drawdown.available ? drawdown.recovery_duration_days : null,
      distribution: rolling.distribution,
    };
  } catch {
    return null;
  }
}

// Shared by the hero cards and the "Most Complete Data" explore tab — kept
// as one function so both call sites hit the exact same fetch() signature
// per fund, letting Next.js's request-level fetch memoization deduplicate
// the network calls instead of fetching each fund twice per page load.
async function loadHeroFunds(): Promise<FundDetail[]> {
  return (await Promise.all(FEATURED_FUND_IDS.map((id) => getFund(id).catch(() => null)))).filter(
    (f): f is FundDetail => f !== null,
  );
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;
  // Defaults to "all" rather than "complete": the hero above already shows
  // the same curated FEATURED_FUND_IDS set that "complete" would repeat
  // here verbatim (identical cards, identical numbers) — on first load
  // that's the same 2-3 funds appearing twice on one screen with zero
  // differentiation. "complete" stays one click away for anyone who
  // deliberately wants to revisit that curated set.
  const activeTab = tab === "complete" ? "complete" : "all";

  return (
    <div className="min-h-screen bg-[var(--canvas)] text-white">
      <SiteHeader />

      <main className="px-8 pt-10 pb-12 max-w-5xl mx-auto space-y-16">
        <section className="space-y-6">
          <div className="max-w-2xl">
            <p className="text-xs font-medium uppercase tracking-wide text-white/50">ThinkFin Decision Intelligence</p>
            <h1 className="mt-2 font-serif text-3xl sm:text-4xl font-semibold leading-tight text-white">
              The return you&rsquo;re shown isn&rsquo;t the return you&rsquo;ll get.
            </h1>
            <p className="mt-3 text-sm text-white/60">
              A single point-to-point CAGR hides drawdowns, recovery time, and the real spread of outcomes. Press{" "}
              <kbd className="rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] font-mono text-white/50">
                ⌘K
              </kbd>{" "}
              to search any fund or run &ldquo;X vs Y&rdquo;.
            </p>
          </div>

          <Suspense fallback={<MythVsRealitySkeleton />}>
            <MythVsRealitySection />
          </Suspense>

          <Suspense fallback={<HeroFundsSkeleton />}>
            <HeroFundsSection />
          </Suspense>
        </section>

        <section className="space-y-4">
          <h2 className="text-sm uppercase tracking-wide text-white/50">Start Here</h2>
          <PersonaCards />
        </section>

        <section className="space-y-4">
          <div className="flex items-baseline justify-between flex-wrap gap-3">
            <h2 className="text-sm uppercase tracking-wide text-white/50">Explore Funds</h2>
            <div className="flex rounded-md border border-[var(--border-subtle)] overflow-hidden text-xs">
              <Link
                href="/?tab=complete"
                className={`px-3 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500 ${
                  activeTab === "complete" ? "bg-blue-500/15 text-blue-300" : "text-white/50 hover:bg-[var(--surface-2)]"
                }`}
              >
                Most Complete Data
              </Link>
              <Link
                href="/?tab=all"
                className={`px-3 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500 ${
                  activeTab === "all" ? "bg-blue-500/15 text-blue-300" : "text-white/50 hover:bg-[var(--surface-2)]"
                }`}
              >
                All Funds
              </Link>
            </div>
          </div>

          <Suspense fallback={<CardGridSkeleton count={activeTab === "all" ? EXPLORE_COUNT : FEATURED_FUND_IDS.length} />}>
            <ExploreFundsGrid activeTab={activeTab} />
          </Suspense>
        </section>

        <section className="space-y-4">
          <h2 className="text-sm uppercase tracking-wide text-white/50">What You Can Do</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {FEATURES.map((feature) => (
              <Link key={feature.href} href={feature.href} className={`${CARD_LINK_CLASS} p-6 space-y-3`}>
                <feature.icon className="h-5 w-5 text-blue-500" />
                <div>
                  <h3 className="text-sm font-semibold text-white">{feature.title}</h3>
                  <p className="text-sm text-white/50 mt-1">{feature.description}</p>
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
  "rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] hover:border-[var(--border-hover)] hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/40 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]";

// Same navy-to-blue gradient as the marketing site's "retirement" goal card
// (anuragyadav9786/new-design's goalVisuals.retirement) — used only for
// fund cards specifically, not the plain CARD_LINK_CLASS cards elsewhere on
// this page, so its own text colors are set explicitly (white-based)
// rather than through the sitewide dark-theme tokens above, which assume
// a near-black card background rather than this navy gradient.
const FUND_CARD_CLASS =
  "rounded-lg border border-white/10 text-white hover:-translate-y-0.5 hover:border-white/20 hover:shadow-lg hover:shadow-black/40 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]";
const FUND_CARD_GRADIENT = "linear-gradient(160deg, #081b33 0%, #123262 55%, #1d5eff 130%)";

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
      <p className="text-sm text-white/50 py-6">
        Featured funds are refreshing —{" "}
        <Link href="/research" className="text-blue-400 underline underline-offset-2 hover:text-blue-300">
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
          <Link
            key={id}
            href={`/research/${id}`}
            className={`${FUND_CARD_CLASS} p-4 space-y-3`}
            style={{ background: FUND_CARD_GRADIENT }}
          >
            <div>
              <p className="text-sm font-medium leading-snug text-white line-clamp-2">{fund.scheme_name}</p>
              <p className="text-xs text-white/70 mt-0.5">
                {fund.amc_name} · {fund.category}
              </p>
            </div>
            <div className="flex items-start justify-between pt-2 border-t border-white/10 text-xs">
              <div>
                <div className="text-white/60">3Y CAGR</div>
                <div className={`font-mono tabular-nums mt-0.5 ${m?.cagr3y != null ? signColorClass(m.cagr3y) : "text-white/40"}`}>
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
                <div className="text-white/60">Max Drawdown</div>
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
  if (funds.length === 0) return <p className="text-sm text-white/50">No funds available yet.</p>;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {funds.map((fund) => {
        const variant = directGrowthVariant(fund);
        return (
          <Link
            key={fund.id}
            href={`/research/${fund.id}`}
            className={`${FUND_CARD_CLASS} p-4 space-y-2`}
            style={{ background: FUND_CARD_GRADIENT }}
          >
            <div>
              <p className="text-sm font-medium leading-snug text-white line-clamp-2">{fund.scheme_name}</p>
              <p className="text-xs text-white/70 mt-0.5">
                {fund.amc_name} · {fund.category}
              </p>
            </div>
            <div className="flex items-baseline justify-between pt-1 border-t border-white/10">
              <span className="text-xs text-white/60">Latest NAV</span>
              <span className="text-sm font-mono tabular-nums text-white">
                {variant?.latest_nav != null ? formatNav(variant.latest_nav) : "—"}
              </span>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

/** The hero's "live example" link + fund cards, split into its own async
 * component so <Suspense> can stream it in independently of the static
 * headline/search bar above it, instead of the whole page waiting on this
 * fetch before sending any HTML. */
async function HeroFundsSection() {
  const [heroFunds, benchmark] = await Promise.all([loadHeroFunds(), loadBenchmarkMetrics()]);

  return (
    <>
      {/* For visitors who don't yet know which fund to search for — a
       * concrete, already-populated example beats an empty search box.
       * Only shown when a real backfilled fund is actually available, so
       * this never links somewhere the fallback state below admits is
       * degraded. */}
      {heroFunds.length > 0 && (
        <Link
          href={`/research/${heroFunds[0].id}`}
          className="mt-5 inline-flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] rounded-sm"
        >
          See a live example: {heroFunds[0].scheme_name} →
        </Link>
      )}

      <div className="mt-8 w-full max-w-4xl text-left">
        <CompleteDataGrid fundIds={FEATURED_FUND_IDS} funds={heroFunds} benchmark={benchmark} />
      </div>
    </>
  );
}

/** Its own async component (see HeroFundsSection above) so a slow myth-vs-
 * reality fetch never blocks the rest of the hero from streaming in first. */
async function MythVsRealitySection() {
  const data = await loadMythVsRealityData(MYTH_VS_REALITY_FUND_ID);

  if (!data) {
    return (
      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-6">
        <h2 className="text-lg font-semibold text-white">Myth vs. Reality</h2>
        <p className="text-sm text-white/50 mt-2">
          This comparison is temporarily unavailable while its fund data refreshes.{" "}
          <Link href="/research/compare" className="text-blue-400 underline underline-offset-2 hover:text-blue-300">
            Compare any two funds yourself →
          </Link>
        </p>
      </div>
    );
  }

  return <MythVsRealityCard fund={data} />;
}

/** The Explore Funds grid + "Browse all" link, split out so the section
 * heading and tab toggle above it (both static, known synchronously from
 * `activeTab`) render immediately instead of waiting on this fetch. */
async function ExploreFundsGrid({ activeTab }: { activeTab: "complete" | "all" }) {
  const [fundCount, benchmark, heroFunds, exploreList] = await Promise.all([
    countFunds().catch(() => ({ count: 0 })),
    loadBenchmarkMetrics(),
    loadHeroFunds(),
    activeTab === "all" ? listFunds({ limit: EXPLORE_COUNT }).catch(() => ({ items: [], has_more: false })) : null,
  ]);

  const featuredFunds =
    activeTab === "complete"
      ? heroFunds
      : (await Promise.all((exploreList?.items ?? []).map((f) => getFund(f.id).catch(() => null)))).filter(
          (f): f is FundDetail => f !== null,
        );

  return (
    <>
      {activeTab === "complete" ? (
        <CompleteDataGrid fundIds={FEATURED_FUND_IDS} funds={featuredFunds} benchmark={benchmark} />
      ) : (
        <AllFundsGrid funds={featuredFunds} />
      )}

      <Link
        href="/research"
        className="inline-block rounded-sm text-xs text-blue-400 hover:text-blue-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]"
      >
        Browse all {fundCount.count.toLocaleString("en-IN")} funds →
      </Link>
    </>
  );
}

function CardGridSkeleton({ count }: { count: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 animate-pulse">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-lg border border-white/10 p-4 space-y-3"
          style={{ background: FUND_CARD_GRADIENT }}
        >
          <div className="h-4 w-3/4 rounded bg-white/15" />
          <div className="h-3 w-1/2 rounded bg-white/15" />
          <div className="flex items-start justify-between pt-2 border-t border-white/10">
            <div className="h-8 w-14 rounded bg-white/15" />
            <div className="h-8 w-14 rounded bg-white/15" />
          </div>
        </div>
      ))}
    </div>
  );
}

function HeroFundsSkeleton() {
  return (
    <div className="mt-8 w-full max-w-4xl">
      <CardGridSkeleton count={FEATURED_FUND_IDS.length} />
    </div>
  );
}

function MythVsRealitySkeleton() {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-6 sm:p-8 space-y-6 animate-pulse">
      <div className="space-y-2">
        <div className="h-3 w-1/3 rounded bg-white/10" />
        <div className="h-3 w-1/4 rounded bg-white/10" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 sm:gap-8">
        <div className="h-24 rounded bg-white/5 border border-[var(--border-subtle)]" />
        <div className="h-24 rounded bg-white/5 border border-[var(--border-subtle)]" />
      </div>
    </div>
  );
}
