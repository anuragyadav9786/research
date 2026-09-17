"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

/** The Tier 3 interaction primitive for the progressive-disclosure metric
 * system — a click-to-reveal for exact numbers that stay hidden by
 * default. Shared by MetricDisclosure (one metric card) and the Rolling
 * Returns section (a full percentile table, not a single scalar). */
export function Disclosure({
  label,
  expandedLabel = "Hide exact numbers",
  children,
}: {
  label: string;
  expandedLabel?: string;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        {expanded ? expandedLabel : label}
        <ChevronDown aria-hidden="true" className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>
      {expanded && <div className="pt-3 mt-1 border-t border-slate-900">{children}</div>}
    </div>
  );
}
