import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { searchSecurities } from "@/lib/api";

export const metadata = { title: "Search by Security — ThinkFin" };

export default async function SecuritiesSearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = q?.trim() ?? "";
  const { items: securities } = query ? await searchSecurities(query) : { items: [] };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="research" />

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-6">
        <div>
          <div className="flex items-center justify-between gap-4">
            <h1 className="text-2xl font-semibold">Search by Security</h1>
            <Link href="/research" className="text-sm text-indigo-400 hover:text-indigo-300 whitespace-nowrap">
              ← Fund Research
            </Link>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Find a stock or bond by name or ISIN, then see every scheme — across any AMC — that holds it.
          </p>
        </div>

        <form method="get" className="flex flex-wrap gap-3">
          <input
            type="text"
            name="q"
            defaultValue={query}
            placeholder="Search by security name or ISIN…"
            className="flex-1 min-w-[200px] rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm placeholder:text-slate-500 focus:outline-none focus:border-slate-600"
          />
          <button
            type="submit"
            className="rounded-md border border-slate-700 bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700"
          >
            Search
          </button>
        </form>

        {query === "" ? (
          <p className="text-slate-500 text-sm py-8">Start typing a security name or ISIN to search.</p>
        ) : securities.length === 0 ? (
          <p className="text-slate-500 text-sm py-8">No securities match &ldquo;{query}&rdquo;.</p>
        ) : (
          <div className="rounded-lg border border-slate-800 divide-y divide-slate-800">
            {securities.map((security) => (
              <Link
                key={security.id}
                href={`/research/securities/${security.id}`}
                className="flex items-center justify-between px-5 py-4 hover:bg-slate-900 transition-colors"
              >
                <div>
                  <div className="font-medium">{security.name}</div>
                  <div className="text-sm text-slate-500 mt-0.5">
                    {security.isin ?? "No ISIN"} {security.sector ? `· ${security.sector.replace(/^Sample: /, "")}` : ""}
                  </div>
                </div>
                <div className="text-sm text-slate-500 text-right">{security.instrument_type ?? "—"}</div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
