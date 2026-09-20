const RESEARCH_STEPS = [
  { id: "overview", label: "1. Overview" },
  { id: "returns", label: "2. Return Behaviour" },
  { id: "risk", label: "3. Risk Behaviour" },
  { id: "consistency", label: "4. Consistency" },
  { id: "market-cycles", label: "5. Market Cycles" },
  { id: "portfolio-impact", label: "6. Portfolio Impact" },
  { id: "summary", label: "7. Research Summary" },
] as const;

/** A fixed 7-step map of the research workflow the page already follows
 * (Discover → Investigate → Compare → Understand), so a reader can jump
 * straight to the section they want instead of scrolling past ones they
 * don't. Plain anchor links — no client-side scroll-spy/JS needed, native
 * browser anchor scrolling handles it; each target section carries a
 * matching scroll-mt-* class (see page.tsx) so it doesn't land hidden
 * under this bar or the sticky site header above it. Horizontally
 * scrollable rather than wrapping, so it stays a single compact bar on a
 * phone-width screen instead of pushing content down. */
export function ResearchStepNav() {
  return (
    <nav
      aria-label="Fund research sections"
      className="sticky top-16 z-10 -mx-8 px-8 py-2 bg-slate-950/95 backdrop-blur border-b border-slate-900 overflow-x-auto"
    >
      <div className="flex gap-4 text-xs whitespace-nowrap w-max">
        {RESEARCH_STEPS.map((step) => (
          <a
            key={step.id}
            href={`#${step.id}`}
            className="text-slate-400 hover:text-slate-100 py-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
          >
            {step.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
