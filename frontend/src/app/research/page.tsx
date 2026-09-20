import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { ExploreResearchFilters } from "@/components/fund/ExploreResearchFilters";
import { ApiError, getDiscoveredFunds, getDiscoveryFilters, listFunds } from "@/lib/api";
import { PERSONAS } from "@/lib/constants";

export const metadata = { title: "Research — ThinkFin" };

const PAGE_SIZE = 50;

export default async function ResearchPage({
  searchParams,
}: {
  searchParams: Promise<{
    search?: string;
    category?: string;
    amc?: string;
    page?: string;
    persona?: string;
    discover?: string;
  }>;
}) {
  const { search, category, amc, page: pageParam, persona: personaId, discover } = await searchParams;
  const page = Math.max(1, Number(pageParam) || 1);

  const { filters: discoveryFilters } = await getDiscoveryFilters().catch(() => ({ filters: [] }));

  // Discover mode is a separate view from the search/category/amc listing
  // below — its results (DiscoverFundsResponse) carry a different shape
  // (a metric_label/metric_value per fund, the "why it's here" evidence)
  // than a plain FundSummary, so the two aren't merged into one list.
  let discoverError: string | null = null;
  const discovered = discover
    ? await getDiscoveredFunds(discover).catch((err) => {
        discoverError = err instanceof ApiError ? err.message : "Could not load this research filter.";
        return null;
      })
    : null;

  const { items: funds, has_more: hasMore } = discover
    ? { items: [], has_more: false }
    : await listFunds({
        search,
        category,
        amc,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });

  // Only trusted when it actually matches the category this persona
  // defines — a stray/stale ?persona= param on an otherwise different
  // filter shouldn't label results with the wrong persona's copy.
  const persona = PERSONAS.find((p) => p.id === personaId && p.categories?.join(",") === category);

  function pageUrlFor(targetPage: number) {
    const qs = new URLSearchParams();
    if (search) qs.set("search", search);
    if (category) qs.set("category", category);
    if (amc) qs.set("amc", amc);
    if (persona) qs.set("persona", persona.id);
    if (targetPage > 1) qs.set("page", String(targetPage));
    const query = qs.toString();
    return query ? `/research?${query}` : "/research";
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="research" />

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Fund Research</h1>
          {!discover && persona && (
            <p className="text-indigo-400 text-sm mt-1">
              {persona.label}: {persona.description}
            </p>
          )}
          {!discover && funds.length > 0 && (
            <p className="text-slate-400 text-sm mt-1">
              Showing {funds.length} fund{funds.length === 1 ? "" : "s"}
              {page > 1 ? ` — page ${page}` : ""}.
            </p>
          )}
        </div>

        <ExploreResearchFilters filters={discoveryFilters} activeKey={discover} />

        {discover ? (
          <div className="space-y-4">
            {discoverError && <p className="text-sm text-rose-400">{discoverError}</p>}

            {discovered && (
              <>
                <div className="rounded-lg border border-slate-800 p-4">
                  <h2 className="text-sm font-semibold text-slate-100">{discovered.label}</h2>
                  <p className="text-sm text-slate-400 mt-1">{discovered.criterion}</p>
                  <p className="text-xs text-slate-600 mt-2">
                    Based on {discovered.funds_scanned} funds checked against this filter — a research filter, not a
                    ranking, and not a claim about every fund on the platform.
                  </p>
                </div>

                {discovered.items.length === 0 ? (
                  <p className="text-slate-500 text-sm py-8">
                    None of the funds checked so far matched this filter yet.
                  </p>
                ) : (
                  <div className="rounded-lg border border-slate-800 divide-y divide-slate-800">
                    {discovered.items.map((item) => (
                      <Link
                        key={item.id}
                        href={`/research/${item.id}`}
                        className="flex items-center justify-between px-5 py-4 hover:bg-slate-900 transition-colors"
                      >
                        <div>
                          <div className="font-medium">{item.scheme_name}</div>
                          <div className="text-sm text-slate-500 mt-0.5">
                            {item.amc_name} · {item.category}
                          </div>
                        </div>
                        <div className="text-sm text-right">
                          <div className="text-slate-500 text-xs">{item.metric_label}</div>
                          <div className="font-mono tabular-nums text-slate-200">{item.metric_value}</div>
                        </div>
                      </Link>
                    ))}
                  </div>
                )}

                <Link href="/research" className="inline-block text-sm text-indigo-400 hover:text-indigo-300">
                  ← Browse all funds
                </Link>
              </>
            )}
          </div>
        ) : (
          <>
            <form method="get" className="flex flex-wrap gap-3">
              <input
                type="text"
                name="search"
                defaultValue={search ?? ""}
                placeholder="Search by scheme name…"
                className="flex-1 min-w-[200px] rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm placeholder:text-slate-500 focus:outline-none focus:border-slate-600"
              />
              <input
                type="text"
                name="amc"
                defaultValue={amc ?? ""}
                placeholder="Filter by AMC…"
                className="min-w-[160px] rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm placeholder:text-slate-500 focus:outline-none focus:border-slate-600"
              />
              <button
                type="submit"
                className="rounded-md border border-slate-700 bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700"
              >
                Search
              </button>
              {(search || category || amc) && (
                <Link
                  href="/research"
                  className="rounded-md border border-slate-800 px-4 py-2 text-sm text-slate-400 hover:text-slate-100"
                >
                  Clear
                </Link>
              )}
            </form>

            {funds.length === 0 ? (
              <p className="text-slate-500 text-sm py-8">No funds match this search.</p>
            ) : (
              <div className="rounded-lg border border-slate-800 divide-y divide-slate-800">
                {funds.map((fund) => (
                  <Link
                    key={fund.id}
                    href={`/research/${fund.id}`}
                    className="flex items-center justify-between px-5 py-4 hover:bg-slate-900 transition-colors"
                  >
                    <div>
                      <div className="font-medium">{fund.scheme_name}</div>
                      <div className="text-sm text-slate-500 mt-0.5">
                        {fund.amc_name} · {fund.category}
                      </div>
                    </div>
                    <div className="text-sm text-slate-500 text-right">
                      {fund.benchmark_name && <div>vs {fund.benchmark_name}</div>}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}

        {!discover && (page > 1 || hasMore) && (
          <div className="flex items-center justify-between pt-2">
            {page > 1 ? (
              <Link
                href={pageUrlFor(page - 1)}
                className="rounded-md border border-slate-800 px-4 py-2 text-sm text-slate-300 hover:border-slate-700 hover:text-slate-100"
              >
                ← Previous
              </Link>
            ) : (
              <span />
            )}
            {hasMore && (
              <Link
                href={pageUrlFor(page + 1)}
                className="rounded-md border border-slate-800 px-4 py-2 text-sm text-slate-300 hover:border-slate-700 hover:text-slate-100"
              >
                Next →
              </Link>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
