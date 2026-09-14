import Link from "next/link";

import { countFunds, getFund, listFunds } from "@/lib/api";
import { formatDate, formatNav } from "@/lib/format";
import type { FundDetail, VariantSummary } from "@/types/fund";

const NAV = [
  { label: "Dashboard", href: "/" },
  { label: "Research", href: "/research" },
  { label: "Compare", href: "/research/compare" },
  { label: "Portfolio", href: "/portfolio" },
  { label: "Market Intelligence", href: "/market" },
  { label: "Reports", href: null },
  { label: "Admin", href: null }, // Data Status dashboard — Phase 3 automation follow-up
];

// A small, fixed-size sample rather than any kind of "top performers" ranking
// — this platform has no popularity/AUM/performance-ranking data to honestly
// back a "top funds" claim, so this only ever promises "funds you can explore",
// never "the best funds".
const FEATURED_COUNT = 6;

const FEATURES = [
  {
    href: "/research",
    title: "Fund Research",
    description: "Returns, risk, rolling returns, and drawdown for any fund — computed from real NAV history.",
  },
  {
    href: "/research/compare",
    title: "Compare Funds",
    description: "Put two funds side by side and see exactly where they diverge.",
  },
  {
    href: "/portfolio",
    title: "Portfolio Analysis",
    description: "Combine several funds into a hypothetical portfolio and see its blended behavior.",
  },
  {
    href: "/market",
    title: "Market Intelligence",
    description: "How funds have historically behaved across bull, bear, and high-volatility periods.",
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

export default async function Home() {
  const [health, fundCount, featuredList] = await Promise.all([
    getBackendHealth(),
    countFunds().catch(() => ({ count: 0 })),
    listFunds({ limit: FEATURED_COUNT }).catch(() => ({ items: [], has_more: false })),
  ]);

  // getFund is scheme-level metadata only — it never touches nav_history or
  // triggers the lazy mfapi.in backfill (see app/api/funds.py), so featuring
  // 6 funds here costs nothing extra even for funds nobody has opened yet.
  const featuredFunds = (
    await Promise.all(featuredList.items.map((f) => getFund(f.id).catch(() => null)))
  ).filter((f): f is FundDetail => f !== null);

  const isHealthy = health.status === "ok";
  const dataAsOf = featuredFunds
    .map((f) => directGrowthVariant(f)?.latest_nav_date)
    .filter((d): d is string => Boolean(d))
    .sort()
    .at(-1);

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-8 py-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <span className="text-lg font-semibold tracking-tight">ThinkFin</span>
        <nav className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-neutral-400">
          {NAV.map((item) =>
            item.href ? (
              <Link key={item.label} href={item.href} className="hover:text-neutral-100">
                {item.label}
              </Link>
            ) : (
              <span key={item.label} className="text-neutral-700" title="Not built yet">
                {item.label}
              </span>
            ),
          )}
        </nav>
      </header>

      <main className="px-8 py-12 max-w-5xl mx-auto space-y-16">
        <section className="space-y-6">
          <div className="space-y-3 max-w-2xl">
            <p className="text-xs uppercase tracking-widest text-cyan-400 font-medium">
              Mutual Fund Decision Intelligence
            </p>
            <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-balance">
              Know what a fund actually delivered — not what it claims to.
            </h1>
            <p className="text-neutral-400">
              Returns, risk, rolling performance, and drawdown for {fundCount.count.toLocaleString("en-IN")} Indian
              mutual funds, computed from official daily NAV data.
            </p>
          </div>

          <form action="/research" className="flex flex-col sm:flex-row gap-3 max-w-xl">
            <input
              type="text"
              name="search"
              placeholder="Search a fund — e.g. Bluechip, Flexicap, Liquid…"
              className="flex-1 rounded-md border border-neutral-800 bg-neutral-900 px-4 py-2.5 text-sm placeholder:text-neutral-600 focus:outline-none focus:border-cyan-700"
            />
            <button
              type="submit"
              className="rounded-md bg-cyan-500 text-neutral-950 font-medium text-sm px-5 py-2.5 hover:bg-cyan-400 transition-colors"
            >
              Search Funds
            </button>
          </form>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-neutral-500">
            <span className="flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${isHealthy ? "bg-emerald-400" : "bg-rose-400"}`} />
              {isHealthy ? "All systems live" : "Backend unreachable"}
            </span>
            {dataAsOf && <span>NAV data updated as of {formatDate(dataAsOf)}</span>}
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm uppercase tracking-wide text-neutral-500">Explore Funds</h2>
            <Link href="/research" className="text-xs text-cyan-400 hover:text-cyan-300">
              Browse all {fundCount.count.toLocaleString("en-IN")} funds →
            </Link>
          </div>
          {featuredFunds.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {featuredFunds.map((fund) => {
                const variant = directGrowthVariant(fund);
                return (
                  <Link
                    key={fund.id}
                    href={`/research/${fund.id}`}
                    className="rounded-lg border border-neutral-800 p-4 space-y-2 hover:border-neutral-700 transition-colors"
                  >
                    <div>
                      <p className="text-sm font-medium leading-snug">{fund.scheme_name}</p>
                      <p className="text-xs text-neutral-500 mt-0.5">
                        {fund.amc_name} · {fund.category}
                      </p>
                    </div>
                    <div className="flex items-baseline justify-between pt-1 border-t border-neutral-900">
                      <span className="text-xs text-neutral-500">Latest NAV</span>
                      <span className="text-sm font-mono">
                        {variant?.latest_nav != null ? formatNav(variant.latest_nav) : "—"}
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-neutral-500">No funds available yet.</p>
          )}
        </section>

        <section className="space-y-4">
          <h2 className="text-sm uppercase tracking-wide text-neutral-500">What You Can Do</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {FEATURES.map((feature) => (
              <Link
                key={feature.href}
                href={feature.href}
                className="rounded-lg border border-neutral-800 p-6 space-y-2 hover:border-neutral-700 transition-colors"
              >
                <h3 className="text-sm font-semibold">{feature.title}</h3>
                <p className="text-sm text-neutral-500">{feature.description}</p>
              </Link>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
