export function formatPct(value: number | null, digits = 2): string {
  if (value === null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatNumber(value: number | null, digits = 2): string {
  if (value === null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "numeric" });
}

export function formatNav(value: number | null): string {
  if (value === null) return "—";
  return `₹${value.toFixed(4)}`;
}

/** Positive-good/negative-bad color, never the sole signal (always paired
 * with a +/- sign in the text itself, per Section 23's UI principles). */
export function signColorClass(value: number | null): string {
  if (value === null) return "text-neutral-400";
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-rose-400";
  return "text-neutral-300";
}
