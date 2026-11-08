"""Manual Motilal Oswal scheme-identity curation.

Motilal Oswal's monthly portfolio-disclosure workbook (see
motilal_disclosure_parser.py) identifies each scheme only by its own
internal fund code (e.g. "YO08", from the workbook's `Index` sheet /
each scheme sheet's own tab name) and its own free-text fund name --
neither of which is guaranteed to match this platform's already-
onboarded `Scheme.name` exactly (e.g. a confirmed real case: "Motilal
Oswal Midcap Fund (Formerly known as Motilal Oswal Midcap 30 Fund)").

This module closes that gap with a human-verified mapping instead of a
live fuzzy text match -- the same deliberate, checked-in-not-inferred
shape as absl_scheme_identity.py / benchmark_curation.py's
SCHEME_BENCHMARK_OVERRIDES, for the same reason: a wrong auto-match here
would misfile a real scheme's entire portfolio disclosure under the
wrong fund, not just omit a data point.

Keyed by Motilal's own stable fund code -- so the matching work is done
ONCE per scheme ever onboarded, not once per month's disclosure.

Populated 2026-11-07 against the real Supabase production database
(`Research.thinkfin`, AMC.name = "Motilal Oswal Mutual Fund", amc_id 87 --
confirmed by query, not assumed) via a scripted exact-match pass, not
hand-typed: every one of the 90 real `IndexEntry` rows the September 2026
disclosure file's `Index` sheet actually contains was normalized (strip
"(Formerly known as ...)" suffixes; fold case; fold whitespace; treat
`-`, `/`, `+`, `:` as word-separators equivalent to a space, same extra
rule ABSL's own curation needed; and -- the one rule beyond what ABSL's
module needed, confirmed necessary because several of Motilal's own
disclosure entries use it as shorthand for their own AMC's full name,
e.g. "MO Nifty MidSmall India Consumption Index Fund" -- expand a leading
"MO " to "Motilal Oswal ") and compared against every onboarded Motilal
Oswal `Scheme.name` normalized the same way. 38 landed on an exact,
unambiguous match (no scheme name normalized to the same key as two
different disclosure entries, or vice versa) and are recorded below.

The remaining 52 short codes are real schemes this disclosure file
genuinely contains but that are NOT onboarded on this platform under any
name that normalizes to a match -- confirmed, not guessed, since the
scheme list queried above is this AMC's complete onboarded set. The
large majority are index-tracking ETFs (Motilal Oswal runs an unusually
large ETF suite -- dozens of single-index ETFs) this platform simply
hasn't onboarded yet, plus a handful of real wording divergences this
module deliberately does NOT auto-normalize past (e.g. the disclosure's
"Nifty MidSmall Fin Servs Index Fund" vs. this platform's onboarded
"Nifty MidSmall Financial Services Index Fund" -- a real abbreviation,
not a formatting difference, left unmapped rather than guessed) and two
confirmed real formatting defects in the disclosure file itself (a
missing space in several "Motilal OswalBSE ..." fund names; the short
code "Y054" instead of the expected "YO54" pattern for one fund -- both
observed directly in the real file, neither affecting mapping since
neither scheme is onboarded here yet regardless). Left out of the table
below rather than guessed at -- per this module's own rule,
`resolve_scheme_for_short_code` reports and skips them until either this
platform onboards the matching `Scheme` or a human confirms a real (not
auto-normalized) name match for one.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.reference import AMC, FundFamily, Scheme

# Keyed by Motilal's own fund code (e.g. "YO08") -> this platform's exact
# Scheme.name -- see module docstring for how this was populated and
# verified against the real Supabase database.
MOTILAL_SCHEME_SHORT_CODE_TO_NAME: dict[str, str] = {
    "YO05": "Motilal Oswal Focused Fund",
    "YO06": "Motilal Oswal Ultra Short Term Fund",
    "YO08": "Motilal Oswal Flexi Cap Fund",
    "YO09": "Motilal Oswal ELSS Tax Saver Fund",
    "YO10": "Motilal Oswal Balanced Advantage Fund",
    "YO16": "Motilal Oswal Nifty Midcap 150 Index Fund",
    "YO17": "Motilal Oswal Nifty Smallcap 250 Index Fund",
    "YO18": "Motilal Oswal Nifty 500 Index Fund",
    "YO19": "Motilal Oswal Nifty Bank Index Fund",
    "YO20": "Motilal Oswal Large and Midcap Fund",
    "YO21": "Motilal Oswal Nifty 50 Index Fund",
    "YO22": "Motilal Oswal Nifty Next 50 Index Fund",
    "YO23": "Motilal Oswal S&P 500 Index Fund",
    "YO27": "Motilal Oswal Asset Allocation Fund of Fund- Conservative",
    "YO28": "Motilal Oswal 5 Year G-Sec Fund of Fund",
    "YO32": "Motilal Oswal Nifty 200 Momentum 30 Index Fund",
    "YO43": "Motilal Oswal Nifty Microcap 250 Index Fund",
    "YO46": "Motilal Oswal Small Cap Fund",
    "YO50": "Motilal Oswal Quant Fund",
    "YO52": "Motilal Oswal Nifty India Defence Index Fund",
    "YO56": "Motilal Oswal Nifty 500 Momentum 50 Index Fund",
    "YO58": "Motilal Oswal Digital India Fund",
    "YO60": "Motilal Oswal Nifty MidSmall India Consumption Index Fund",
    "YO61": "Motilal Oswal Nifty MidSmall Healthcare Index Fund",
    "YO62": "Motilal Oswal Nifty MidSmall IT and Telecom Index Fund",
    "YO63": "Motilal Oswal Nifty Capital Market Index Fund",
    "YO64": "Motilal Oswal Arbitrage Fund",
    "YO65": "Motilal Oswal Innovation Opportunities Fund",
    "YO66": "Motilal Oswal Active Momentum Fund",
    "YO68": "Motilal Oswal Infrastructure Fund",
    "YO72": "Motilal Oswal Services Fund",
    "YO78": "Motilal Oswal BSE 1000 Index Fund",
    "YO80": "Motilal Oswal Special Opportunities Fund",
    "YO82": "Motilal Oswal Consumption Fund",
    "YO89": "Motilal Oswal Financial Services Fund",
    "YO92": "Motilal Oswal Contra Fund",
    "YO93": "Motilal Oswal BSE Clean Environment Index Fund",
    "YO97": "Motilal Oswal Quality Fund",
}


def resolve_scheme_for_short_code(db: Session, amc_name: str, short_code: str) -> Scheme | None:
    """The already-onboarded Scheme this Motilal Oswal fund code
    identifies, or None if it isn't in
    MOTILAL_SCHEME_SHORT_CODE_TO_NAME yet -- a real, expected condition
    for any scheme not yet curated, which the caller must report and
    skip, never guess a match for.

    `amc_name` is the exact `AMC.name` this platform actually onboarded
    Motilal Oswal under -- passed in by the caller rather than assumed
    here. Scoping to this AMC is a safety net against a same-named scheme
    existing under a different fund house, not just a lookup
    convenience."""
    scheme_name = MOTILAL_SCHEME_SHORT_CODE_TO_NAME.get(short_code)
    if scheme_name is None:
        return None
    return (
        db.query(Scheme)
        .join(FundFamily, Scheme.fund_family_id == FundFamily.id)
        .join(AMC, FundFamily.amc_id == AMC.id)
        .filter(AMC.name == amc_name, Scheme.name == scheme_name)
        .first()
    )
