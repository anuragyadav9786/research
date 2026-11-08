import Link from "next/link";
import { notFound } from "next/navigation";

import { SiteHeader } from "@/components/layout/SiteHeader";
import { ApiError, getAmc } from "@/lib/api";
import { formatDate } from "@/lib/format";

export async function generateMetadata({ params }: { params: Promise<{ amcId: string }> }) {
  const { amcId } = await params;
  try {
    const amc = await getAmc(Number(amcId));
    return { title: `${amc.name} — ThinkFin` };
  } catch {
    return { title: "AMC — ThinkFin" };
  }
}

export default async function AmcDetailPage({ params }: { params: Promise<{ amcId: string }> }) {
  const { amcId: amcIdParam } = await params;
  const amcId = Number(amcIdParam);
  if (!Number.isInteger(amcId)) notFound();

  let amc;
  try {
    amc = await getAmc(amcId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const schemesWithHoldings = amc.schemes.filter((s) => s.holdings_as_of_date !== null).length;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="research" />

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-6">
        <div>
          <Link href="/research/amcs" className="text-sm text-indigo-400 hover:text-indigo-300">
            ← Browse by AMC
          </Link>
          <h1 className="text-2xl font-semibold mt-2">{amc.name}</h1>
          <p className="text-slate-400 text-sm mt-1">
            {amc.schemes.length} scheme{amc.schemes.length === 1 ? "" : "s"} · {schemesWithHoldings} with real
            portfolio-holdings data loaded
          </p>
        </div>

        {amc.schemes.length === 0 ? (
          <p className="text-slate-500 text-sm py-8">This AMC has no onboarded schemes yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-2 font-medium">Scheme</th>
                  <th className="px-4 py-2 font-medium">Category</th>
                  <th className="px-4 py-2 font-medium">Fund Family</th>
                  <th className="px-4 py-2 font-medium">Holdings Data</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {amc.schemes.map((scheme) => (
                  <tr key={scheme.id} className="hover:bg-slate-900 transition-colors">
                    <td className="px-4 py-2">
                      <Link href={`/research/${scheme.id}`} className="hover:text-indigo-400">
                        {scheme.scheme_name}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-slate-400">{scheme.category}</td>
                    <td className="px-4 py-2 text-slate-400">{scheme.fund_family_name}</td>
                    <td className="px-4 py-2 text-slate-400">
                      {scheme.holdings_as_of_date ? (
                        <span className="text-emerald-400">{formatDate(scheme.holdings_as_of_date)}</span>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
