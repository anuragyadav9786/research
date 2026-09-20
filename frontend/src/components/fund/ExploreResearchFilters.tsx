import Link from "next/link";

import type { DiscoveryFilterSummary } from "@/types/fund";

/** The "1,833 funds problem" fix (product-upgrade brief Section 8): a row
 * of named research filters instead of an unfiltered, alphabetical wall
 * of funds. Each is a real, stated criterion a fund either does or
 * doesn't meet — never a "Top 10" or a score, so this renders the
 * criterion as a link's own title text, not a rank. */
export function ExploreResearchFilters({
  filters,
  activeKey,
}: {
  filters: DiscoveryFilterSummary[];
  activeKey?: string;
}) {
  if (filters.length === 0) return null;

  return (
    <div>
      <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-2">Explore Research</h2>
      <div className="flex flex-wrap gap-2">
        {filters.map((filter) => (
          <Link
            key={filter.key}
            href={`/research?discover=${filter.key}`}
            title={filter.criterion}
            className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
              filter.key === activeKey
                ? "border-indigo-700 bg-indigo-900/40 text-indigo-200"
                : "border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-100"
            }`}
          >
            {filter.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
