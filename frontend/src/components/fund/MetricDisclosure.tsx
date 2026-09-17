import { Disclosure } from "@/components/fund/Disclosure";

/** A metric card built around progressive disclosure: Tier 1 (a plain-
 * English sentence) and Tier 2 (a shared-scale visual bar) are always
 * visible — a 5-second read needs no interaction. Tier 3 (exact numbers /
 * full percentile spread) sits behind a click, for whoever wants the
 * precision instead of just the read. */
export function MetricDisclosure({
  label,
  value,
  valueClassName = "",
  sentence,
  tier2,
  tier3,
  tier3Label = "Show exact numbers",
}: {
  label: string;
  value: string;
  valueClassName?: string;
  sentence: string;
  tier2: React.ReactNode;
  tier3?: React.ReactNode;
  tier3Label?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wide text-slate-500">{label}</h3>
        <span className={`text-sm font-mono tabular-nums font-semibold ${valueClassName}`}>{value}</span>
      </div>
      <p className="text-sm text-slate-300">{sentence}</p>
      {tier2}
      {tier3 && <Disclosure label={tier3Label}>{tier3}</Disclosure>}
    </div>
  );
}
