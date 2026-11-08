import Link from "next/link";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { listAmcs } from "@/lib/api";

export const metadata = { title: "Browse by AMC — ThinkFin" };

// No params/searchParams to make this dynamic automatically (unlike
// /research or /research/[fundId]) -- without this, Next.js tries to
// statically prerender it at build time and the fetch to the backend
// fails wherever the backend isn't reachable at build time (e.g. CI).
export const dynamic = "force-dynamic";

export default async function AmcsPage() {
  const { items: amcs } = await listAmcs();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="research" />

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-6">
        <div>
          <div className="flex items-center justify-between gap-4">
            <h1 className="text-2xl font-semibold">Browse by AMC</h1>
            <Link href="/research" className="text-sm text-indigo-400 hover:text-indigo-300 whitespace-nowrap">
              ← Fund Research
            </Link>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            {amcs.length} AMC{amcs.length === 1 ? "" : "s"} on the platform.
          </p>
        </div>

        {amcs.length === 0 ? (
          <p className="text-slate-500 text-sm py-8">No AMCs found.</p>
        ) : (
          <div className="rounded-lg border border-slate-800 divide-y divide-slate-800">
            {amcs.map((amc) => (
              <Link
                key={amc.id}
                href={`/research/amcs/${amc.id}`}
                className="flex items-center justify-between px-5 py-4 hover:bg-slate-900 transition-colors"
              >
                <div>
                  <div className="font-medium">{amc.name}</div>
                  <div className="text-sm text-slate-500 mt-0.5">
                    {amc.fund_family_count} fund famil{amc.fund_family_count === 1 ? "y" : "ies"} ·{" "}
                    {amc.scheme_count} scheme{amc.scheme_count === 1 ? "" : "s"}
                  </div>
                </div>
                <div className="text-sm text-right text-slate-500">
                  {amc.schemes_with_holdings_count} / {amc.scheme_count} with holdings data
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
