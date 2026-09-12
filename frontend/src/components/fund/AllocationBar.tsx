import { formatNumber } from "@/lib/format";
import type { AllocationSlice } from "@/types/portfolio";

// A small fixed palette, cycled — enough categories in practice (sectors,
// market-cap buckets) that a data-driven color scale would be overkill.
const COLORS = [
  "bg-cyan-700", "bg-emerald-700", "bg-amber-700", "bg-violet-700",
  "bg-rose-700", "bg-sky-700", "bg-lime-700", "bg-fuchsia-700", "bg-neutral-600",
];

export function AllocationBar({ slices }: { slices: AllocationSlice[] }) {
  if (slices.length === 0) {
    return <p className="text-sm text-neutral-500">No allocation data available.</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex h-6 w-full overflow-hidden rounded">
        {slices.map((slice, i) => (
          <div
            key={slice.label}
            className={COLORS[i % COLORS.length]}
            style={{ width: `${slice.weight_pct}%` }}
            title={`${slice.label}: ${formatNumber(slice.weight_pct, 1)}%`}
          />
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-neutral-400">
        {slices.map((slice, i) => (
          <li key={slice.label} className="flex items-center gap-1.5">
            <span className={`inline-block h-2.5 w-2.5 rounded-sm ${COLORS[i % COLORS.length]}`} />
            {slice.label.replace(/^Sample: /, "").replace(/_/g, " ")} · {formatNumber(slice.weight_pct, 1)}%
          </li>
        ))}
      </ul>
    </div>
  );
}
