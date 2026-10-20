import Link from "next/link";
import { TrendingDown, TrendingUp } from "lucide-react";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { ApiError, getFundScreener } from "@/lib/api";
import { formatDate, formatPct } from "@/lib/format";
import { SCREENER_PERIODS, type ScreenerPeriod } from "@/types/fund";

export const metadata = { title: "Top Performers — ThinkFin" };

const CARD_LIMIT = 24;

const PERIOD_LABELS: Record<ScreenerPeriod, string> = {
  "1m": "1 Month", "3m": "3 Month", "6m": "6 Month", "1y": "1 Year", "3y": "3 Year", "5y": "5 Year",
};

function isScreenerPeriod(value: string | undefined): value is ScreenerPeriod {
  return !!value && (SCREENER_PERIODS as readonly string[]).includes(value);
}

export default async function TopPerformersPage({
  searchParams,
}: {
  searchParams: Promise<{ period?: string }>;
}) {
  const { period: periodParam } = await searchParams;
  const period: ScreenerPeriod = isScreenerPeriod(periodParam) ? periodParam : "1y";

  let error: string | null = null;
  const screener = await getFundScreener(period, "desc", CARD_LIMIT).catch((err) => {
    error = err instanceof ApiError ? err.message : "Could not load top performers.";
    return null;
  });

  const cards = (screener?.items ?? []).filter((item) => item.returns[period].status === "VALID");

  return (
    <div className="min-h-screen bg-[var(--canvas)] text-white">
      <SiteHeader active="research" />
      <main className="max-w-5xl mx-auto px-4 sm:px-8 py-10 space-y-6">
        <div className="max-w-2xl">
          <h1 className="font-serif text-2xl sm:text-3xl font-semibold text-white">Top Performers</h1>
          <p className="mt-2 text-sm text-white/60">
            The {CARD_LIMIT} highest real returns over the selected period, across Regular Plan, Growth-option
            funds. Simple point-to-point returns (not XIRR or time-weighted) — see{" "}
            <Link href="/methodology" className="text-blue-400 hover:text-blue-300">
              Data &amp; Methodology
            </Link>{" "}
            for how these differ from the rest of this site&rsquo;s fund-level analytics. Historical performance
            does not indicate future results, and nothing here is investment advice.
          </p>
        </div>

        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Lookback period">
          {SCREENER_PERIODS.map((p) => (
            <Link
              key={p}
              href={`/research/top-performers?period=${p}`}
              role="tab"
              aria-selected={period === p}
              className={`rounded-md border px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] ${
                period === p
                  ? "border-blue-500 bg-blue-500/15 text-blue-300"
                  : "border-[var(--border-subtle)] bg-[var(--surface-1)] text-white/60 hover:border-[var(--border-hover)] hover:text-white"
              }`}
            >
              {PERIOD_LABELS[p]}
            </Link>
          ))}
        </div>

        {error && <p className="text-sm text-rose-400">{error}</p>}

        {screener && (
          <>
            {screener.as_of_date && (
              <p className="text-xs text-white/40">As of {formatDate(screener.as_of_date)}</p>
            )}

            {cards.length === 0 ? (
              <p className="text-sm text-white/50">
                Not enough funds have {PERIOD_LABELS[period].toLowerCase()} of history yet to show here — try a
                shorter period.
              </p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {cards.map((item) => {
                  const cell = item.returns[period];
                  const positive = (cell.return_pct ?? 0) >= 0;
                  const Icon = positive ? TrendingUp : TrendingDown;
                  return (
                    <Link
                      key={item.id}
                      href={`/research/${item.id}`}
                      title={cell.anchor_date ? `Measured from ${formatDate(cell.anchor_date)}` : undefined}
                      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] hover:border-[var(--border-hover)] hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/40 transition-all p-4 space-y-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]"
                    >
                      <div>
                        <h3 className="text-sm font-semibold text-white leading-snug">{item.scheme_name}</h3>
                        <span className="mt-1.5 inline-block rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/60">
                          {item.category}
                        </span>
                      </div>
                      <div
                        className={`flex items-center gap-1.5 pt-2 border-t border-white/10 font-mono tabular-nums text-lg font-semibold ${
                          positive ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        <Icon aria-hidden="true" className="h-4 w-4" />
                        {formatPct(cell.return_pct)}
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
