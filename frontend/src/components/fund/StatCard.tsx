export function StatCard({
  label,
  value,
  valueClassName = "",
  hint,
  ariaLabel,
}: {
  label: string;
  value: string;
  valueClassName?: string;
  hint?: string;
  /** Overrides the default label/value/hint screen-reader announcement —
   * for a card whose meaning isn't fully carried by its visible text
   * alone (e.g. distinguishing why a value is unavailable). */
  ariaLabel?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 p-4" aria-label={ariaLabel} role={ariaLabel ? "group" : undefined}>
      <div className="text-xs uppercase tracking-wide text-slate-500" aria-hidden={ariaLabel ? true : undefined}>
        {label}
      </div>
      <div className={`text-lg font-semibold mt-1 ${valueClassName}`} aria-hidden={ariaLabel ? true : undefined}>
        {value}
      </div>
      {hint && (
        <div className="text-xs text-slate-500 mt-1" aria-hidden={ariaLabel ? true : undefined}>
          {hint}
        </div>
      )}
    </div>
  );
}
