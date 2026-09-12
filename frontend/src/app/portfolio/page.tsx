import Link from "next/link";

import { listFunds } from "@/lib/api";
import { PortfolioAnalysisForm } from "@/components/portfolio/PortfolioAnalysisForm";

export const metadata = { title: "Portfolio Analysis — ThinkFin" };

export default async function PortfolioAnalysisPage() {
  const funds = await listFunds();

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-8 py-4 flex items-center justify-between">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          ThinkFin
        </Link>
        <nav className="flex gap-6 text-sm text-neutral-400">
          <Link href="/" className="hover:text-neutral-100">Dashboard</Link>
          <Link href="/research" className="hover:text-neutral-100">Research</Link>
          <Link href="/research/compare" className="hover:text-neutral-100">Compare</Link>
          <Link href="/portfolio" className="text-neutral-100">Portfolio</Link>
        </nav>
      </header>

      <main className="px-8 py-10 max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Portfolio Analysis</h1>
          <p className="text-neutral-400 text-sm mt-1">
            Combine 2-10 funds by weight to see the look-through holdings, concentration, overlap and
            portfolio-level risk that no single fund page shows on its own.
          </p>
        </div>

        {funds.length < 2 ? (
          <p className="text-sm text-neutral-500">Need at least 2 funds in the dataset to analyse a portfolio.</p>
        ) : (
          <PortfolioAnalysisForm funds={funds} />
        )}
      </main>
    </div>
  );
}
