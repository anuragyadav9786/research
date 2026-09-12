import Link from "next/link";

import { listFunds } from "@/lib/api";

export const metadata = { title: "Research — ThinkFin" };

export default async function ResearchPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; category?: string; amc?: string }>;
}) {
  const { search, category, amc } = await searchParams;
  const funds = await listFunds({ search, category, amc });

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-8 py-4 flex items-center justify-between">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          ThinkFin
        </Link>
        <nav className="flex gap-6 text-sm text-neutral-400">
          <Link href="/" className="hover:text-neutral-100">Dashboard</Link>
          <Link href="/research" className="text-neutral-100">Research</Link>
          <Link href="/research/compare" className="hover:text-neutral-100">Compare</Link>
          <Link href="/portfolio" className="hover:text-neutral-100">Portfolio</Link>
        </nav>
      </header>

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Fund Research</h1>
          <p className="text-neutral-400 text-sm mt-1">
            {funds.length} fund{funds.length === 1 ? "" : "s"} covered in the current dataset.
          </p>
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
      </main>
    </div>
  );
}
