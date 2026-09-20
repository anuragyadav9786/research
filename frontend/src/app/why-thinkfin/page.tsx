import Link from "next/link";
import { Activity, GitCompare, Layers, TrendingUp, Waves } from "lucide-react";

import { SiteHeader } from "@/components/layout/SiteHeader";

export const metadata = { title: "Why ThinkFin — ThinkFin" };

const FRAMEWORK_STEPS = [
  {
    icon: TrendingUp,
    title: "Return",
    description:
      "What did the fund actually earn, over more than one measurement window — not just a single point-to-point figure that depends entirely on the day you happen to measure from.",
  },
  {
    icon: Activity,
    title: "Risk",
    description:
      "How severe were its historical declines, and how long did it take to recover from them? A strong long-term return can coexist with a significant temporary loss along the way.",
  },
  {
    icon: Waves,
    title: "Consistency",
    description:
      "How much did the outcome vary depending on when you invested? Rolling returns across every historical entry date show the real spread of outcomes, not one lucky (or unlucky) snapshot.",
  },
  {
    icon: GitCompare,
    title: "Behaviour",
    description:
      "How did the fund actually behave relative to its benchmark and category — during calm periods and during market stress — not just whether it beat a number on paper.",
  },
  {
    icon: Layers,
    title: "Portfolio Impact",
    description:
      "How does this fund interact with what you already hold? Two funds that each look diversified individually can combine into a portfolio that isn't.",
  },
] as const;

/** The product-upgrade brief's Section 11 — explaining ThinkFin's product
 * philosophy through its actual analytical framework, not an unsupported
 * comparison to competitors. Every claim here points at a real, already-
 * shipped feature (linked below) rather than describing something
 * aspirational. */
export default function WhyThinkFinPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <SiteHeader />

      <main className="px-8 py-10 max-w-3xl mx-auto space-y-10">
        <div>
          <h1 className="text-2xl font-semibold">Why ThinkFin?</h1>
          <p className="text-slate-400 text-sm mt-2">
            Not a claim that ThinkFin is better than any other research tool — an explanation of the question this
            platform is actually built to answer, and why that question is different from the one most fund
            research starts with.
          </p>
        </div>

        <section className="rounded-lg border border-slate-800 p-6 space-y-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Traditional research asks</p>
            <p className="text-lg font-serif text-slate-200 mt-1">&ldquo;What return did the fund generate?&rdquo;</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">ThinkFin asks</p>
            <p className="text-lg font-serif text-white mt-1">
              &ldquo;What did the investor experience while earning that return?&rdquo;
            </p>
          </div>
          <p className="text-sm text-slate-400 pt-2 border-t border-slate-900">
            A single CAGR figure can be technically accurate and still hide the exact experience that mattered to
            someone actually holding the fund — a sharp temporary loss, a long wait to recover, or a return that
            depended entirely on the specific day they happened to invest.
          </p>
        </section>

        <section>
          <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-4">The Framework</h2>
          <div className="space-y-4">
            {FRAMEWORK_STEPS.map((step, i) => (
              <div key={step.title} className="flex gap-4">
                <div className="flex flex-col items-center flex-shrink-0">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-800 text-slate-400">
                    <step.icon className="h-4 w-4" />
                  </div>
                  {i < FRAMEWORK_STEPS.length - 1 && <div className="w-px flex-1 bg-slate-800 mt-2" />}
                </div>
                <div className="pb-4">
                  <h3 className="text-sm font-semibold text-slate-100">{step.title}</h3>
                  <p className="text-sm text-slate-400 mt-1">{step.description}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">What ThinkFin does not do</h2>
          <ul className="text-sm text-slate-400 space-y-1.5 list-disc list-inside">
            <li>It does not tell you what to invest in, or recommend buying, holding, or selling anything.</li>
            <li>It does not produce arbitrary scores, rankings, or labels like &ldquo;Best Fund&rdquo; or &ldquo;Winner.&rdquo;</li>
            <li>It does not guarantee future results from historical behaviour.</li>
          </ul>
          <p className="text-sm text-slate-400 mt-3">
            ThinkFin should not tell you what to invest in. It should help you understand what you are investing in.
          </p>
        </section>

        <section>
          <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-3">See it in practice</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <Link
              href="/research"
              className="rounded-lg border border-slate-800 p-4 hover:border-slate-700 transition-colors"
            >
              <div className="font-medium text-slate-100">Research a fund</div>
              <div className="text-slate-500 mt-1">
                See the full Return → Risk → Consistency → Behaviour → Portfolio Impact breakdown for any fund.
              </div>
            </Link>
            <Link
              href="/methodology"
              className="rounded-lg border border-slate-800 p-4 hover:border-slate-700 transition-colors"
            >
              <div className="font-medium text-slate-100">Data &amp; Methodology</div>
              <div className="text-slate-500 mt-1">Exactly how every figure on this platform is calculated.</div>
            </Link>
          </div>
        </section>

        <p className="text-xs text-slate-600 border-t border-slate-900 pt-4">
          ThinkFin is a research tool, not investment advice.
        </p>
      </main>
    </div>
  );
}
