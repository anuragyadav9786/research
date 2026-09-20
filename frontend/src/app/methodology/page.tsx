import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";

export const metadata = { title: "Data & Methodology — ThinkFin" };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      <div className="mt-2 space-y-3 text-sm text-slate-300">{children}</div>
    </section>
  );
}

/** The product-upgrade brief's Section 10 — a dedicated, investor-facing
 * page for how ThinkFin's numbers are actually produced. The underlying
 * facts here already exist as developer-facing documentation
 * (docs/data-sources.md, docs/analytics-methodology.md) and as per-
 * response disclaimer/methodology_note fields scattered across the API —
 * this page doesn't compute anything new, it translates and consolidates
 * what's already true into plain English in one place. */
export default function MethodologyPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader />

      <main className="px-8 py-10 max-w-3xl mx-auto space-y-10">
        <div>
          <h1 className="text-2xl font-semibold">Data &amp; Methodology</h1>
          <p className="text-slate-400 text-sm mt-2">
            Every number on this platform is either real, ingested market data or explicitly labelled sample data —
            never a blend presented as if it were one thing. This page explains where the data comes from, how
            often it updates, and exactly how each metric is calculated.
          </p>
        </div>

        <Section title="Where the NAV data comes from">
          <p>
            Fund NAV (Net Asset Value) history comes from two real sources, both published by or sourced from AMFI
            (the Association of Mutual Funds in India):
          </p>
          <ul className="list-disc list-inside space-y-1.5">
            <li>
              <span className="text-slate-100 font-medium">AMFI&rsquo;s daily NAV feed</span> (NAVAll.txt) — the
              day&rsquo;s NAV for every fund in India, published once per business day directly by AMFI.
            </li>
            <li>
              <span className="text-slate-100 font-medium">api.mfapi.in</span> — a third-party service that
              republishes AMFI&rsquo;s own official historical NAV data, used to backfill a fund&rsquo;s full price
              history the first time its research page is viewed (not on a schedule).
            </li>
          </ul>
          <p>
            Some funds on this platform are currently sample data — entirely fictional funds used to demonstrate
            the platform while real data onboarding is in progress. Sample funds are always named distinctly (e.g.
            &ldquo;Northbridge&rdquo;, &ldquo;Meridian&rdquo;) and their AMC name is explicitly suffixed &ldquo;(Sample
            Data)&rdquo; wherever it appears — they are never presented as if they were real, investable funds.
          </p>
        </Section>

        <Section title="How often the data updates">
          <p>
            The live AMFI feed updates once per business day, matching AMFI&rsquo;s own publishing schedule. A
            fund&rsquo;s full historical backfill happens once, on-demand, the first time its research page is
            requested — after that, its history is stored and reused rather than re-fetched. Every fund detail page
            shows <span className="text-slate-100 font-medium">&ldquo;Latest NAV… as of [date]&rdquo;</span> next to
            its current NAV, so you always know exactly how current the figures you&rsquo;re looking at are.
          </p>
        </Section>

        <Section title="Benchmark methodology">
          <p>
            Where a fund has a stated benchmark index (e.g. Nifty 50 TRI, Nifty Midcap 150 TRI), all benchmark
            comparisons on that fund&rsquo;s page — returns, drawdown, beta, alpha, capture ratios — are computed
            from that fund&rsquo;s own actual linked benchmark series, not a generic stand-in index. The one
            exception is the homepage, where a single representative index fund is used so several different
            funds can be shown against one consistent reference point.
          </p>
        </Section>

        <Section title="Rolling-return methodology">
          <p>
            A rolling return answers: &ldquo;if I had invested for this exact holding period starting on any
            historical date, what would my return have been?&rdquo; ThinkFin computes this for every historically
            possible starting date and reports the full spread — worst, 10th/25th/median/75th/90th percentile, and
            best outcome — rather than a single figure. This is what &ldquo;Consistency&rdquo; means throughout
            this platform: how much the outcome varied depending on when you happened to invest.
          </p>
        </Section>

        <Section title="Drawdown and recovery calculation">
          <p>
            <span className="text-slate-100 font-medium">Maximum drawdown</span> is the single worst peak-to-trough
            decline in a fund&rsquo;s NAV history — the largest fall from a previous high point before a new
            recovery. <span className="text-slate-100 font-medium">Recovery period</span> is the number of days
            from that trough until the NAV climbed back to its pre-drawdown peak. A fund that hasn&rsquo;t yet
            climbed back is shown as &ldquo;not yet recovered,&rdquo; never a fabricated recovery date.
          </p>
        </Section>

        <Section title="Treatment of missing or invalid NAVs">
          <p>
            Any incoming NAV record with a missing field, a non-numeric or non-positive value, an unparseable date,
            or a duplicate entry for a date already recorded is rejected before it ever reaches this platform&rsquo;s
            database — it is never guessed at, interpolated, or silently defaulted to zero. A metric that needs
            more history than a fund currently has (e.g. a 5-year return for a fund with 3 years of data) is shown
            as &ldquo;not enough NAV history yet,&rdquo; never as a misleading N/A treated as zero.
          </p>
        </Section>

        <Section title="Fund mergers and renaming">
          <p>
            ThinkFin does not yet have a documented, automated process for detecting and handling fund mergers or
            scheme renaming events. If a real-world fund merges into another or changes its name, its historical
            data may currently appear inconsistent or be attributed to the wrong scheme identity until this is
            explicitly built. This is a known, stated limitation rather than a silently unhandled edge case.
          </p>
        </Section>

        <Section title="Historical-data limitations">
          <ul className="list-disc list-inside space-y-1.5">
            <li>Real AMFI data ingestion for this platform is recent — many funds don&rsquo;t yet have enough history for long-horizon metrics (5Y/7Y/10Y returns, rolling windows). This is shown honestly rather than hidden.</li>
            <li>Market-cycle behaviour uses the platform&rsquo;s own sample-data date windows for its illustrative regimes, not verified real-world market classifications, wherever sample data is involved — every market-cycle response repeats this as an explicit note.</li>
            <li>Stress-test scenarios only model shocks this platform has real exposure data for (broad market, sector, market-cap concentration). Interest-rate, recession, currency, and inflation scenarios are explicitly marked as not modeled rather than estimated with invented sensitivity figures.</li>
            <li>Sharpe and Sortino ratios currently assume a fixed 7% annual risk-free rate — a documented placeholder, not a live rate feed.</li>
          </ul>
        </Section>

        <Section title="Illustrative examples vs. real figures">
          <p>
            Wherever this platform translates a percentage into a rupee amount (for example, &ldquo;a hypothetical
            ₹10,00,000 investment&rdquo;), that rupee figure is explicitly labelled illustrative — it applies a
            fund&rsquo;s real, computed percentage to a round, easy-to-follow principal, not a projection, a real
            investor&rsquo;s actual holding, or a recommendation. The underlying percentage itself is always real,
            computed data.
          </p>
        </Section>

        <p className="text-xs text-slate-600 border-t border-slate-900 pt-4">
          ThinkFin is a research tool, not investment advice. Historical performance does not guarantee future
          results.{" "}
          <Link href="/why-thinkfin" className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2">
            Why ThinkFin? →
          </Link>
        </p>
      </main>
    </div>
  );
}
