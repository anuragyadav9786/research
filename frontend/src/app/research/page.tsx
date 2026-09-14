import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { listFunds } from "@/lib/api";

export const metadata = { title: "Research — ThinkFin" };

const PAGE_SIZE = 50;

export default async function ResearchPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; category?: string; amc?: string; page?: string }>;
}) {
  const { search, category, amc, page: pageParam } = await searchParams;
  const page = Math.max(1, Number(pageParam) || 1);
  const { items: funds, has_more: hasMore } = await listFunds({
    search,
    category,
    amc,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  function pageUrlFor(targetPage: number) {
    const qs = new URLSearchParams();
    if (search) qs.set("search", search);
    if (category) qs.set("category", category);
    if (amc) qs.set("amc", amc);
    if (targetPage > 1) qs.set("page", String(targetPage));
    const query = qs.toString();
    return query ? `/research?${query}` : "/research";
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <SiteHeader active="research" />

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Fund Research</h1>
          {funds.length > 0 && (
            <p className="text-neutral-400 text-sm mt-1">
              Showing {funds.length} fund{funds.length === 1 ? "" : "s"}
              {page > 1 ? ` — page ${page}` : ""}.
            </p>
          )}
        </div>

        <form method="get" className="flex flex-wrap gap-3">
          <input
            type="text"
            name="search"
            defaultValue={search ?? ""}
            placeholder="Search by scheme name…"
            className="flex-1 min-w-[200px] rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm placeholder:text-neutral-500 focus:outline-none focus:border-neutral-600"
          />
          <input
            type="text"
            name="amc"
            defaultValue={amc ?? ""}
            placeholder="Filter by AMC…"
            className="min-w-[160px] rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm placeholder:text-neutral-500 focus:outline-none focus:border-neutral-600"
          />
          <button
            type="submit"
            className="rounded-md border border-neutral-700 bg-neutral-800 px-4 py-2 text-sm hover:bg-neutral-700"
          >
            Search
          </button>
          {(search || category || amc) && (
            <Link
              href="/research"
              className="rounded-md border border-neutral-800 px-4 py-2 text-sm text-neutral-400 hover:text-neutral-100"
            >
              Clear
            </Link>
          )}
        </form>

        {funds.length === 0 ? (
          <p className="text-neutral-500 text-sm py-8">No funds match this search.</p>
        ) : (
          <div className="rounded-lg border border-neutral-800 divide-y divide-neutral-800">
            {funds.map((fund) => (
              <Link
                key={fund.id}
                href={`/research/${fund.id}`}
                className="flex items-center justify-between px-5 py-4 hover:bg-neutral-900 transition-colors"
              >
                <div>
                  <div className="font-medium">{fund.scheme_name}</div>
                  <div className="text-sm text-neutral-500 mt-0.5">
                    {fund.amc_name} · {fund.category}
                  </div>
                </div>
                <div className="text-sm text-neutral-500 text-right">
                  {fund.benchmark_name && <div>vs {fund.benchmark_name}</div>}
                </div>
              </Link>
            ))}
          </div>
        )}

        {(page > 1 || hasMore) && (
          <div className="flex items-center justify-between pt-2">
            {page > 1 ? (
              <Link
                href={pageUrlFor(page - 1)}
                className="rounded-md border border-neutral-800 px-4 py-2 text-sm text-neutral-300 hover:border-neutral-700 hover:text-neutral-100"
              >
                ← Previous
              </Link>
            ) : (
              <span />
            )}
            {hasMore && (
              <Link
                href={pageUrlFor(page + 1)}
                className="rounded-md border border-neutral-800 px-4 py-2 text-sm text-neutral-300 hover:border-neutral-700 hover:text-neutral-100"
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
