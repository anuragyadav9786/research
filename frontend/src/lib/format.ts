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

/** Month + year only — "Aug 2025" — for dates that should read as an
 * approximate period, not an exact day (e.g. "no NAV history before…"). */
export function formatMonthYear(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-IN", { year: "numeric", month: "short" });
}

export function formatNav(value: number | null): string {
  if (value === null) return "—";
  return `₹${value.toFixed(4)}`;
}

/** Whole-rupee amounts in lakh (₹1,00,000), the unit Indian investors
 * actually think in for a portfolio-sized number — a raw ₹ figure with
 * five zeros reads as "count the zeros," not "understand the number." */
export function formatLakh(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `₹${(value / 100000).toFixed(2)} lakh`;
}

/** Positive-good/negative-bad color, never the sole signal (always paired
 * with a +/- sign in the text itself, per Section 23's UI principles). */
export function signColorClass(value: number | null): string {
  if (value === null) return "text-slate-400";
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-rose-400";
  return "text-slate-300";
}
