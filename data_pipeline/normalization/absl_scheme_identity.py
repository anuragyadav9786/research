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

Populated 2026-11-07 against the real Supabase production database
(`Research.thinkfin`, AMC.name = "Aditya Birla Sun Life Mutual Fund",
amc_id 59 -- confirmed by query, not assumed) via a scripted exact-match
pass, not hand-typed: every one of the 104 real `IndexEntry` rows the
September 2026 disclosure file's `Index` sheet actually contains was
normalized (strip "(FORMERLY KNOWN AS ...)" suffixes; fold case; fold
whitespace; and -- the one extra rule beyond the module's original
plan, needed because the disclosure file and this platform's own
onboarding punctuate the same scheme differently, e.g. "SDL+AAA PSU-APR
2027" vs "SDL + AAA PSU - APR 2027", "Multi-Asset" vs "Multi  Asset" --
treat `-`, `/`, `+`, `:` as word-separators equivalent to a space, same
as whitespace) and compared against every onboarded ABSL `Scheme.name`
normalized the same way. 82 landed on an exact, unambiguous match (no
scheme name normalized to the same key as two different disclosure
entries, or vice versa) and are recorded below.

The remaining 22 short codes are real schemes this disclosure file
genuinely contains but that are NOT onboarded on this platform under
any name that normalizes to a match -- confirmed, not guessed, since
the scheme list queried above is this AMC's complete onboarded set.
Almost all of them are ETF variants of an already-mapped non-ETF scheme
(e.g. "GOLDETF"/"NIFTYETF"/"SILVRETF" alongside the already-mapped
"GOLDFOF" Gold Fund, Nifty 50 Index Fund, Silver ETF FOF) or
index/FOF schemes this platform simply hasn't onboarded yet: GOLDETF,
NIFTYETF, SENSXETF, NIFYNX50, BSLPHF, BANKETF, NHLTHETF, NITETF,
SILVRETF, SILVRFOF, FTPTQ, N30MTETF, N30QTETF, COFAIETF, ABSLUS03,
ABSLUS10, CIGAPR33, NPSEETF, CBGETF, C10YGETF, MSCIETF, BSE10ETF. Left
out of the table below rather than guessed at -- per this module's own
rule, `resolve_scheme_for_short_code` reports and skips them until
either this platform onboards the matching `Scheme` or a human confirms
a real (not auto-normalized) name match for one.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.reference import AMC, FundFamily, Scheme

# Keyed by ABSL's own short code (e.g. "BSLEQTY") -> this platform's
# exact Scheme.name -- see module docstring for how this was populated
# and verified against the real Supabase database.
ABSL_SCHEME_SHORT_CODE_TO_NAME: dict[str, str] = {
    "ABBSEIIF": "Aditya Birla Sun Life BSE India Infrastructure Index Fund",
    "ABSLBCF": "Aditya Birla Sun Life Business Cycle Fund",
    "ABSLCONF": "Aditya Birla Sun Life Conglomerate Fund",
    "ABSLESG": "Aditya Birla Sun Life ESG Integration Strategy Fund",
    "ABSLLDF": "Aditya Birla Sun Life Long Term Fund",
    "ABSLMAAF": "Aditya Birla Sun Life Multi Asset Allocation Fund",
    "ABSLMCF": "Aditya Birla Sun Life Multi-Cap Fund",
    "ABSLQF": "Aditya Birla Sun Life Quant Fund",
    "ABSLSO": "Aditya Birla Sun Life Special Opportunities Fund",
    "ABSLTNLF": "Aditya Birla Sun Life Transportation and Logistics Fund",
    "ADVG": "Aditya Birla Sun Life Large & Mid Cap Fund",
    "BBIF": "Aditya Birla Sun Life Short Term Fund",
    "BBP": "Aditya Birla Sun Life Ultra Short Term Fund",
    "BDB": "Aditya Birla Sun Life Dynamic Term Fund",
    "BDYP": "Aditya Birla Sun Life Dividend Yield Fund",
    "BFL": "Aditya Birla Sun Life Floating Interest Rates Fund",
    "BFS": "Aditya Birla Sun Life Money Market Fund",
    "BINFRA": "Aditya Birla Sun Life Infrastructure Fund",
    "BINTEQA": "Aditya Birla Sun Life International Equity Fund",
    "BMIDX50": "Aditya Birla Sun Life BSE 500 Momentum 50 Index Fund",
    "BQIDX50": "Aditya Birla Sun Life BSE 500 Quality 50 Index Fund",
    "BSL95F": "Aditya Birla Sun Life Aggressive Hybrid Fund",
    "BSLAAMM": "Aditya Birla Sun Life Multi Asset Omni FoF",
    "BSLADMM": "Aditya Birla Sun Life Income Plus Arbitrage Active FOF",
    "BSLBBYW": "ADITYA BIRLA SUN LIFE BAL BHAVISHYA YOJNA",
    "BSLBKFS": "Aditya Birla Sun Life Banking and Financial Services Fund",
    "BSLCBF": "Aditya Birla Sun Life Credit Risk Fund",
    "BSLCM": "Aditya Birla Sun Life Ultra short to short term Fund",
    "BSLDAAF": "Aditya Birla Sun Life Balanced Advantage Fund",
    "BSLEAF": "ADITYA BIRLA SUN LIFE ARBITRAGE FUND",
    "BSLEQSF": "Aditya Birla Sun Life Equity Savings Fund",
    "BSLEQTY": "Aditya Birla Sun Life Flexi Cap Fund",
    "BSLFEF": "Aditya Birla Sun Life Large Cap Fund",
    "BSLFPAP": "Aditya Birla Sun Life Dynamic Asset Allocation Omni FOF",
    "BSLFPCP": "Aditya Birla Sun Life Conservative Hybrid Active FOF",
    "BSLFPPP": "Aditya Birla Sun Life Aggressive Hybrid Omni FOF",
    "BSLGCF": "Aditya Birla Sun Life Global Emerging Opportunities Fund",
    "BSLGRE": "Aditya Birla Sun Life Global Excellence Equity Fund Of Fund",
    "BSLIF": "Aditya Birla Sun Life Corporate Bond Fund",
    "BSLMFG": "Aditya Birla Sun Life Manufacturing Equity Fund",
    "BSLMIFOF": "Aditya Birla Sun Life Multi-Asset Passive FOF",
    "BSLMTP": "Aditya Birla Sun Life Medium Term Fund",
    "BSLNMF": "Aditya Birla Sun Life Digital India Fund",
    "BSLONF": "ADITYA BIRLA SUN LIFE OVERNIGHT FUND",
    "BSLR96": "Aditya Birla Sun Life ELSS Tax Saver Fund",
    "BSLRF30": "Aditya Birla Sun Life Retirement Fund-The 30s Plan",
    "BSLRF40": "Aditya Birla Sun Life Retirement Fund-The 40s Plan",
    "BSLRF50": "Aditya Birla Sun Life Retirement Fund-The 50s Plan",
    "BSLRF50P": "Aditya Birla Sun Life Retirement Fund-The 50s Plus-Debt Plan",
    "BSLSTF": "Aditya Birla Sun Life Banking & PSU Debt Fund",
    "BSLTA1": "Aditya Birla Sun Life Small Cap Fund",
    "BTOP100": "Aditya Birla Sun Life Focused Fund",
    "CASH": "Aditya Birla Sun Life Liquid Fund",
    "CIGAPR28": "Aditya Birla Sun Life Crisil IBX Gilt Apr 2028 Index Fund",
    "CIGAPR29": "Aditya Birla Sun Life Crisil IBX Gilt -Apr 2029 Index Fund",
    "CIGJUN27": "Aditya Birla Sun Life Crisil IBX Gilt June 2027 Index Fund",
    "CIGPSA28": "Aditya Birla Sun Life Crisil IBX 50:50 Gilt Plus SDL Apr 2028 Index Fund",
    "CISJUN32": "Aditya Birla Sun Life CRISIL IBX SDL Jun 2032 Index Fund",
    "CSFSD12": "Aditya Birla Sun Life Crisil-IBX Financial Services 9-12 Months Debt Index Fund",
    "CSFSD6": "Aditya Birla Sun Life Crisil-IBX Financial Services 3 to 6 months Debt Index Fund",
    "CSFSI27": "Aditya Birla Sun Life Crisil-IBX AAA Financial Services Index-Sep 2027 Fund",
    "CSNHFS26": "Aditya Birla Sun Life Crisil-IBX AAA NBFC-HFC INDEX-Sep 2026 Fund",
    "CSPAPA27": "Aditya Birla Sun Life Crisil IBX 60:40 SDL+AAA PSU-APR 2027 Index Fund",
    "GENNEXT": "Aditya Birla Sun Life Consumption Fund",
    "GOLDFOF": "Aditya Birla Sun Life Gold Fund",
    "INV": "Aditya Birla Sun Life Gilt Fund",
    "MIDCAP": "Aditya Birla Sun Life Midcap Fund",
    "MIP25": "Aditya Birla Sun Life Conservative Hybrid Fund",
    "MNC": "Aditya Birla Sun Life MNC Fund",
    "NEWIF50": "Aditya Birla Sun Life Nifty 50 Equal Weight index Fund",
    "NIFTY": "Aditya Birla Sun Life Nifty 50 Index Fund",
    "NINDDEF": "Aditya Birla Sun Life Nifty India Defence Index Fund",
    "NMID150": "Aditya Birla Sun Life Nifty Midcap 150 Index Fund",
    "NSDAPR27": "Aditya Birla Sun Life Nifty SDL Apr 2027 Index Fund",
    "NSDAQ100": "Aditya Birla Sun Life US Equity Passive FOF",
    "NSDSEP27": "Aditya Birla Sun Life Nifty SDL SEP 2027 Index Fund",
    "NSMALL50": "Aditya Birla Sun Life Nifty Smallcap 50 Index Fund",
    "NSPPBS26": "Aditya Birla Sun Life Nifty SDL Plus PSU Bond SEP 2026 60:40 Index Fund",
    "NXTIDX50": "Aditya Birla Sun Life Nifty Next 50 Index Fund",
    "PLUS": "Aditya Birla Sun Life Medium to Long Term Fund",
    "PSUEQ": "Aditya Birla Sun Life PSU Equity Fund",
    "PURE": "Aditya Birla Sun Life Value Fund",
}


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
