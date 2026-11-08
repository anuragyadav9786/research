import Link from "next/link";
import { notFound } from "next/navigation";

import { HoldersTable } from "@/components/fund/HoldersTable";
import { StatCard } from "@/components/fund/StatCard";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { ApiError, getSecurityHolders } from "@/lib/api";

export async function generateMetadata({ params }: { params: Promise<{ securityId: string }> }) {
  const { securityId } = await params;
  try {
    const { security } = await getSecurityHolders(Number(securityId));
    return { title: `${security.name} — ThinkFin` };
  } catch {
    return { title: "Security — ThinkFin" };
  }
}

export default async function SecurityDetailPage({ params }: { params: Promise<{ securityId: string }> }) {
  const { securityId: securityIdParam } = await params;
  const securityId = Number(securityIdParam);
  if (!Number.isInteger(securityId)) notFound();

  let data;
  try {
    data = await getSecurityHolders(securityId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const { security, holders, total_holders: totalHolders } = data;
  const amcCount = new Set(holders.map((h) => h.amc_name)).size;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader active="research" />

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-6">
        <div>
          <Link href="/research/securities" className="text-sm text-indigo-400 hover:text-indigo-300">
            ← Search by Security
          </Link>
          <h1 className="text-2xl font-semibold mt-2">{security.name}</h1>
          <p className="text-slate-400 text-sm mt-1">
            {security.isin ?? "No ISIN"} {security.sector ? `· ${security.sector.replace(/^Sample: /, "")}` : ""}{" "}
            {security.instrument_type ? `· ${security.instrument_type}` : ""}
          </p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <StatCard label="Held By" value={`${totalHolders} scheme${totalHolders === 1 ? "" : "s"}`} />
          <StatCard label="Across" value={`${amcCount} AMC${amcCount === 1 ? "" : "s"}`} />
        </div>

        {holders.length === 0 ? (
          <p className="text-slate-500 text-sm py-8">
            No scheme currently discloses this security in its latest portfolio.
          </p>
        ) : (
          <div>
            <h2 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Holders</h2>
            <HoldersTable holders={holders} />
          </div>
        )}
      </main>
    </div>
  );
}
