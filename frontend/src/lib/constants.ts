// Substrings of real AMFI-style category text (e.g. "Equity Scheme -
// Large Cap Fund", "Equity Schemes - Large Cap Fund" — AMCs don't agree on
// "Scheme" vs "Schemes"), matched via /research's category filter (a
// case-insensitive substring match, not exact — see fund_repository.py) so
// a single fixed label like "Large Cap" still works across every AMC's own
// wording. Shared between the homepage and the command bar's category
// shortcut.
export const FUND_CATEGORIES = ["Large Cap", "Flexi Cap", "Mid Cap", "Small Cap", "Debt"];

export interface Persona {
  id: string;
  label: string;
  description: string;
  /** Category substrings, OR'd together by /api/funds' comma-separated
   * category filter (see fund_repository.py's `_category_filter`) — e.g.
   * "Small Cap,Mid Cap" for a persona spanning both. Omitted when `href`
   * points somewhere other than a category-filtered /research list. */
  categories?: string[];
  /** Overrides the generated /research?category=... link entirely — used
   * by "Check Portfolio Overlap", which isn't a fund list at all. */
  href?: string;
}

// The homepage's 4 persona quick-start cards. Each is a real, honest
// entry point built on what this platform can actually verify today:
// AMFI's own equity/debt category taxonomy (asset class is a legitimate
// first-order risk lens — debt/hybrid carries materially less NAV
// volatility than small-cap equity) rather than per-fund downside-capture
// or rolling-return thresholds, which aren't cheaply computable across
// the whole fund universe at list-query time (see fund_metrics — a
// precomputed cache table with no populating job wired up yet, so it's
// always empty; live-computing risk for every fund in a category on each
// request isn't viable). "Aggressive Horizon" and "Check Portfolio
// Overlap" already had a real, existing home (category filter and the
// /portfolio analysis flow, respectively) — no new capability needed for
// those two.
export const PERSONAS: Persona[] = [
  {
    id: "capital-preservation",
    label: "Low Panic, Capital Preservation",
    description: "Debt and conservative-hybrid funds built to protect capital first — smaller swings, steadier NAV.",
    // "Conservative Hybrid", not bare "Hybrid" — the latter would also
    // sweep in "Aggressive Hybrid Fund"/"Balanced Hybrid Fund", which
    // carry meaningfully more equity risk than this persona is for.
    categories: ["Debt", "Conservative Hybrid"],
  },
  {
    id: "consistent-compounders",
    label: "Consistent Compounders",
    description: "Diversified large-cap and flexi-cap equity — built for steady compounding over sharp swings.",
    categories: ["Large Cap", "Flexi Cap"],
  },
  {
    id: "aggressive-horizon",
    label: "Aggressive, 7+ Year Horizon",
    description: "Small-cap and mid-cap equity — higher volatility, for money you won't need for years.",
    categories: ["Small Cap", "Mid Cap"],
  },
  {
    id: "check-overlap",
    label: "Check Portfolio Overlap",
    description: "Already hold a few funds? See how much they actually overlap before adding another.",
    href: "/portfolio",
  },
];
