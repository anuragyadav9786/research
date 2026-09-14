import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { RealityCheckWidget, type RealityCheckFund } from "@/components/fund/RealityCheckWidget";
import { countFunds, getFund, getFundDrawdown, getFundReturns, getFundRollingReturns, listFunds } from "@/lib/api";
import { formatDate, formatNav } from "@/lib/format";
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

const EXPLORE_COUNT = 6;

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

async function getBackendHealth() {
  const url = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${url}/api/health`, { cache: "no-store" });
    if (!res.ok) return { status: "unreachable" };
    return res.json();
  } catch {
    return { status: "unreachable" };
  }
}

function directGrowthVariant(fund: FundDetail): VariantSummary | undefined {
  return fund.variants.find((v) => v.plan === "direct" && v.option === "growth") ?? fund.variants[0];
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

  const [health, fundCount, realityA, realityB, exploreList] = await Promise.all([
    getBackendHealth(),
    countFunds().catch(() => ({ count: 0 })),
    loadRealityCheckFund(REALITY_CHECK_PAIR[0]),
    loadRealityCheckFund(REALITY_CHECK_PAIR[1]),
    activeTab === "all" ? listFunds({ limit: EXPLORE_COUNT }).catch(() => ({ items: [], has_more: false })) : null,
  ]);

  const featuredFunds =
    activeTab === "complete"
      ? (await Promise.all(FEATURED_FUND_IDS.map((id) => getFund(id).catch(() => null)))).filter(
          (f): f is FundDetail => f !== null,
        )
      : (await Promise.all((exploreList?.items ?? []).map((f) => getFund(f.id).catch(() => null)))).filter(
          (f): f is FundDetail => f !== null,
        );

  const isHealthy = health.status === "ok";
  const dataAsOf = featuredFunds
    .map((f) => directGrowthVariant(f)?.latest_nav_date)
    .filter((d): d is string => Boolean(d))
    .sort()
    .at(-1);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="dashboard" />

      <main className="px-8 py-12 max-w-5xl mx-auto space-y-16">
        <section className="space-y-6">
          <div className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 rounded-full border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-400">
            <span className="flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${isHealthy ? "bg-emerald-500 animate-pulse" : "bg-rose-500"}`} />
              {isHealthy ? "Live AMFI NAV Sync" : "Backend unreachable"}
            </span>
            <span className="text-slate-700">|</span>
            <span>Zero Sponsor Bias</span>
            <span className="text-slate-700">|</span>
            <span>100% Independent Analytics</span>
          </div>

          <div className="space-y-3 max-w-2xl">
            <h1 className="text-3xl sm:text-5xl font-semibold tracking-tight text-slate-100 text-balance">
              Know how your fund actually behaves when the market drops.
            </h1>
            <p className="text-base text-slate-400 leading-relaxed">
              Institutional-grade rolling returns, maximum drawdown, and stress testing for{" "}
              {fundCount.count.toLocaleString("en-IN")} Indian mutual funds — calculated directly from daily NAV
              history.
            </p>
          </div>

          <form action="/research" className="flex flex-col sm:flex-row gap-3 max-w-xl">
            <div className="relative flex-1">
              <input
                type="text"
                name="search"
                placeholder="Search by fund name, AMC, or category (e.g., Parag Parikh Flexi Cap)…"
                className="w-full rounded-md border border-slate-800 bg-slate-900 pl-4 pr-16 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-600"
              />
              <kbd className="hidden sm:inline-flex absolute right-3 top-1/2 -translate-y-1/2 items-center rounded border border-slate-700 px-1.5 py-0.5 text-[10px] font-mono text-slate-500">
                Enter ↵
              </kbd>
            </div>
            <button
              type="submit"
              className="rounded-md bg-indigo-500 text-white font-medium text-sm px-5 py-2.5 hover:bg-indigo-400 transition-colors"
            >
              Search Funds
            </button>
          </form>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500 mr-1">Quick probe:</span>
            {featuredFunds
              .filter((f) => (FEATURED_FUND_IDS as readonly number[]).includes(f.id))
              .map((fund) => (
                <Link
                  key={fund.id}
                  href={`/research/${fund.id}`}
                  className="rounded-full border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-300 hover:border-indigo-700 hover:text-indigo-300 transition-colors"
                >
                  {fund.scheme_name}
                </Link>
              ))}
          </div>

          {dataAsOf && <p className="text-xs text-slate-600">NAV data updated as of {formatDate(dataAsOf)}</p>}
        </section>

        {realityA && realityB && <RealityCheckWidget fundA={realityA} fundB={realityB} />}

        <section className="space-y-4">
          <div className="flex items-baseline justify-between flex-wrap gap-3">
            <h2 className="text-sm uppercase tracking-wide text-slate-500">Explore Funds</h2>
            <div className="flex rounded-md border border-slate-800 overflow-hidden text-xs">
              <Link
                href="/?tab=complete"
                className={`px-3 py-1.5 ${
                  activeTab === "complete" ? "bg-indigo-900/50 text-indigo-200" : "text-slate-400 hover:bg-slate-900"
                }`}
              >
                Most Complete Data
              </Link>
              <Link
                href="/?tab=all"
                className={`px-3 py-1.5 ${
                  activeTab === "all" ? "bg-indigo-900/50 text-indigo-200" : "text-slate-400 hover:bg-slate-900"
                }`}
              >
                All Funds
              </Link>
            </div>
          </div>

          {activeTab === "complete" ? (
            <CompleteDataGrid fundIds={FEATURED_FUND_IDS} funds={featuredFunds} />
          ) : (
            <AllFundsGrid funds={featuredFunds} />
          )}

          <Link href="/research" className="inline-block text-xs text-indigo-400 hover:text-indigo-300">
            Browse all {fundCount.count.toLocaleString("en-IN")} funds →
          </Link>
        </section>

        <section className="space-y-4">
          <h2 className="text-sm uppercase tracking-wide text-slate-500">What You Can Do</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {FEATURES.map((feature) => (
              <Link
                key={feature.href}
                href={feature.href}
                className="rounded-lg border border-slate-800 p-6 space-y-3 hover:border-slate-700 transition-colors"
              >
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

async function CompleteDataGrid({ fundIds, funds }: { fundIds: readonly number[]; funds: FundDetail[] }) {
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
            className="rounded-lg border border-slate-800 p-4 space-y-3 hover:border-slate-700 transition-colors"
          >
            <div>
              <p className="text-sm font-medium leading-snug text-slate-100 line-clamp-2">{fund.scheme_name}</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {fund.amc_name} · {fund.category}
              </p>
            </div>
            <div className="flex items-center justify-between pt-2 border-t border-slate-900 text-xs">
              <div>
                <div className="text-slate-500">3Y CAGR</div>
                <div className="font-mono tabular-nums text-slate-100 mt-0.5">
                  {m?.cagr3y != null ? `${m.cagr3y.toFixed(1)}%` : "—"}
                </div>
              </div>
              <div className="text-right">
                <div className="text-slate-500">Max Drawdown</div>
                <div className="font-mono tabular-nums text-rose-400 mt-0.5">
                  {m?.maxDrawdown != null ? `${m.maxDrawdown.toFixed(1)}%` : "—"}
                </div>
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
          <Link
            key={fund.id}
            href={`/research/${fund.id}`}
            className="rounded-lg border border-slate-800 p-4 space-y-2 hover:border-slate-700 transition-colors"
          >
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
