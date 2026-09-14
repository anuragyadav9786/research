import { SiteHeader } from "@/components/layout/SiteHeader";
import { listAllFunds } from "@/lib/api";
import { PortfolioAnalysisForm } from "@/components/portfolio/PortfolioAnalysisForm";

export const metadata = { title: "Portfolio Analysis — ThinkFin" };
export const dynamic = "force-dynamic";

export default async function PortfolioAnalysisPage() {
  const funds = await listAllFunds();

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <SiteHeader active="portfolio" />

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
