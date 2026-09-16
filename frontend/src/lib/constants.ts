// Substrings of real AMFI-style category text (e.g. "Equity Scheme -
// Large Cap Fund", "Equity Schemes - Large Cap Fund" — AMCs don't agree on
// "Scheme" vs "Schemes"), matched via /research's category filter (a
// case-insensitive substring match, not exact — see fund_repository.py) so
// a single fixed label like "Large Cap" still works across every AMC's own
// wording. Shared between the homepage and the command bar's category
// shortcut.
export const FUND_CATEGORIES = ["Large Cap", "Flexi Cap", "Mid Cap", "Small Cap", "Debt"];
