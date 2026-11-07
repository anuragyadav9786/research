"""Manual ABSL scheme-identity curation.

ABSL's monthly portfolio-disclosure workbook (see
absl_disclosure_parser.py) identifies each scheme only by its own
internal short code (e.g. "BSLEQTY", from the workbook's `Index` sheet /
each scheme sheet's own tab name) and its own free-text scheme name --
neither of which is guaranteed to match this platform's already-
onboarded `Scheme.name` exactly (AMFI's own scheme-onboarding naming can
differ in wording from ABSL's disclosure naming, e.g. a confirmed real
case: "ADITYA BIRLA SUN LIFE AGGRESSIVE HYBRID FUND (FORMERLY KNOWN AS
ADITYA BIRLA SUN LIFE EQUITY HYBRID '95 FUND)").

This module closes that gap with a human-verified mapping instead of a
live fuzzy text match -- the same deliberate, checked-in-not-inferred
shape as benchmark_curation.py's SCHEME_BENCHMARK_OVERRIDES, for the
same reason: a wrong auto-match here would misfile a real scheme's
entire portfolio disclosure under the wrong fund, not just omit a data
point.

Keyed by ABSL's own stable short code -- confirmed to stay the same for
a given scheme across at least two real monthly disclosures' `Index`
sheets this session inspected -- not by scheme name, so the matching
work is done ONCE per scheme ever onboarded, not once per month's
disclosure.

Intentionally empty until filled in with sourced entries -- never
pre-populated with a guessed scheme_id here. To populate: for each
`IndexEntry` `absl_disclosure_parser.parse_index_sheet(file_bytes)`
returns, find the `Scheme` row under ABSL's own `AMC` row whose name
matches (after stripping "(FORMERLY KNOWN AS ...)" suffixes and folding
case/whitespace) -- an EXACT match only, never "close enough" -- and add
that `(short_code -> Scheme.name)` pair here. A short code seen in a
real file that isn't in this table yet must be reported as unmapped and
skipped by the caller, never auto-matched.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.reference import AMC, FundFamily, Scheme

# Keyed by ABSL's own short code (e.g. "BSLEQTY") -> this platform's
# exact Scheme.name. Empty until filled in with sourced, human-verified
# entries -- see module docstring for how.
ABSL_SCHEME_SHORT_CODE_TO_NAME: dict[str, str] = {}


def resolve_scheme_for_short_code(db: Session, amc_name: str, short_code: str) -> Scheme | None:
    """The already-onboarded Scheme this ABSL short code identifies, or
    None if it isn't in ABSL_SCHEME_SHORT_CODE_TO_NAME yet -- a real,
    expected condition for any scheme not yet curated, which the caller
    must report and skip, never guess a match for.

    `amc_name` is the exact `AMC.name` this platform actually onboarded
    Aditya Birla Sun Life under -- passed in by the caller rather than
    assumed here, since this module has never been run against a real
    database and that exact string hasn't been confirmed. Scoping to
    this AMC is a safety net against a same-named scheme existing under
    a different fund house, not just a lookup convenience."""
    scheme_name = ABSL_SCHEME_SHORT_CODE_TO_NAME.get(short_code)
    if scheme_name is None:
        return None
    return (
        db.query(Scheme)
        .join(FundFamily, Scheme.fund_family_id == FundFamily.id)
        .join(AMC, FundFamily.amc_id == AMC.id)
        .filter(AMC.name == amc_name, Scheme.name == scheme_name)
        .first()
    )
