"""Create real AMC/FundFamily/Scheme/SchemeVariant rows for schemes present
in AMFI's NAVAll.txt that don't yet exist in our database.

This intentionally supersedes scheme_mapping.py's original stance of never
auto-creating scheme identity from a NAV file alone. That concern — AMFI's
flat row not reliably carrying curated identity — is addressed here by
parsing conservatively (see scheme_identity.py) and skipping anything
ambiguous, rather than by never attempting it at all. Every value used
(AMC name, category, scheme name, Plan, Option, AMFI code, ISIN) comes
directly from the file's own columns; nothing is invented.

One real limitation, not papered over: AMFI's file carries only one level
of fund-house identity (the AMC name printed above each block of schemes).
Our schema also wants a FundFamily beneath the AMC (Section 16-17), so
FundFamily here is created with the same name as its AMC rather than an
invented sub-grouping the source data doesn't provide.

Also deliberately growth-only: an IDCW (dividend) option is recognized
here (see scheme_identity.py's parse_option) specifically so it can be
skipped, not onboarded — this platform's users research and invest in
growth-option funds only, so there is no reason to carry IDCW variants'
identity or NAV history at all.

Records skipped here (unparseable plan/option — most ETFs and Bonus-option
variants among them; a recognized-but-unwanted IDCW option; or a missing/
unrecognized category) are reported back so the caller can log *why*,
never silently dropped.

Performance note: this batches new-row creation per level (AMC, then
FundFamily, then Scheme, then SchemeVariant) via a single multi-row
INSERT...RETURNING each, instead of one INSERT + round trip per row. A
first version did one `db.flush()` per new row; against a real full AMFI
file (thousands of new schemes on first run) that meant thousands of
network round trips to a remote database and a single onboarding run
taking 20+ minutes in a long-lived, uncommitted transaction — genuinely
risky, not just slow, given how easily that overruns a pooled connection's
own limits. Batching cuts that to a small, fixed number of round trips
regardless of file size.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models.reference import AMC, FundFamily, Scheme, SchemeVariant
from data_pipeline.normalization.scheme_identity import parse_category_header, parse_option, parse_plan
from data_pipeline.sources.amfi.parser import RawNavRecord


@dataclass
class SkippedScheme:
    scheme_code: str
    scheme_name: str
    reason: str


@dataclass
class OnboardingResult:
    amcs_created: int = 0
    fund_families_created: int = 0
    schemes_created: int = 0
    variants_created: int = 0
    skipped: list[SkippedScheme] = field(default_factory=list)


@dataclass
class _Candidate:
    scheme_code: str
    amc_name: str
    base_name: str
    category: str
    plan: str
    option: str
    isin: str | None


def _classify(raw_records: list[RawNavRecord], known_amfi_codes: set[str], known_isins: set[str], result: OnboardingResult) -> list[_Candidate]:
    """Pure, in-memory pass: decide what to skip and what to onboard,
    without touching the database. Guards against a scheme code or ISIN
    appearing twice within the same file — the batched inserts below
    would otherwise violate a unique constraint and fail the whole batch."""
    candidates: list[_Candidate] = []
    seen_scheme_codes: set[str] = set()
    seen_isins: set[str] = set()

    for rec in raw_records:
        isin = rec.isin_growth or rec.isin_div_reinvestment

        if rec.scheme_code in known_amfi_codes or (isin and isin in known_isins):
            continue  # already onboarded in a previous run

        if not rec.scheme_code or not rec.amc_name:
            result.skipped.append(SkippedScheme(rec.scheme_code, rec.scheme_name, "missing scheme code or AMC name"))
            continue

        base_name = rec.scheme_name.strip()
        if not base_name:
            result.skipped.append(SkippedScheme(rec.scheme_code, rec.scheme_name, "missing scheme name"))
            continue

        category = parse_category_header(rec.category) if rec.category else None
        if not category:
            result.skipped.append(SkippedScheme(rec.scheme_code, rec.scheme_name, "unrecognized category header"))
            continue

        plan = parse_plan(rec.plan_raw)
        if plan is None:
            result.skipped.append(
                SkippedScheme(rec.scheme_code, rec.scheme_name, f"could not determine plan from {rec.plan_raw!r}")
            )
            continue

        option = parse_option(rec.option_raw)
        if option is None:
            result.skipped.append(
                SkippedScheme(rec.scheme_code, rec.scheme_name, f"could not determine option from {rec.option_raw!r}")
            )
            continue

        if option == "idcw":
            # This platform only tracks growth-option variants — IDCW
            # (dividend) plans are deliberately never onboarded, not just
            # hidden after the fact, so nav_history never accumulates data
            # for them in the first place.
            result.skipped.append(SkippedScheme(rec.scheme_code, rec.scheme_name, "idcw_option_not_tracked"))
            continue

        if rec.scheme_code in seen_scheme_codes:
            continue  # duplicate scheme code within this same file — keep the first
        seen_scheme_codes.add(rec.scheme_code)

        if isin and isin in seen_isins:
            isin = None  # duplicate ISIN within this file — drop it rather than fail the unique constraint
        elif isin:
            seen_isins.add(isin)

        candidates.append(
            _Candidate(
                scheme_code=rec.scheme_code,
                amc_name=rec.amc_name,
                base_name=base_name,
                category=category,
                plan=plan,
                option=option,
                isin=isin,
            )
        )

    return candidates


def onboard_schemes(db: Session, raw_records: list[RawNavRecord]) -> OnboardingResult:
    result = OnboardingResult()

    known_amfi_codes = {v.amfi_code for v in db.query(SchemeVariant.amfi_code).all() if v.amfi_code}
    known_isins = {v.isin for v in db.query(SchemeVariant.isin).all() if v.isin}

    candidates = _classify(raw_records, known_amfi_codes, known_isins, result)
    if not candidates:
        return result

    # ---- AMCs ----
    amc_id_by_name: dict[str, int] = {a.name: a.id for a in db.query(AMC.id, AMC.name).all()}
    new_amc_names = sorted({c.amc_name for c in candidates} - amc_id_by_name.keys())
    if new_amc_names:
        rows = db.execute(
            insert(AMC).returning(AMC.id, AMC.name),
            [{"name": name} for name in new_amc_names],
        ).all()
        amc_id_by_name.update({name: amc_id for amc_id, name in rows})
        result.amcs_created = len(new_amc_names)

    # ---- FundFamilies (mirrors its AMC's name — see module docstring) ----
    family_id_by_key: dict[tuple[int, str], int] = {
        (f.amc_id, f.name): f.id for f in db.query(FundFamily.id, FundFamily.amc_id, FundFamily.name).all()
    }
    needed_family_keys = {(amc_id_by_name[c.amc_name], c.amc_name) for c in candidates}
    new_family_keys = sorted(k for k in needed_family_keys if k not in family_id_by_key)
    if new_family_keys:
        rows = db.execute(
            insert(FundFamily).returning(FundFamily.id, FundFamily.amc_id, FundFamily.name),
            [{"amc_id": amc_id, "name": name} for amc_id, name in new_family_keys],
        ).all()
        family_id_by_key.update({(amc_id, name): family_id for family_id, amc_id, name in rows})
        result.fund_families_created = len(new_family_keys)

    # ---- Schemes ----
    scheme_id_by_key: dict[tuple[int, str], int] = {
        (s.fund_family_id, s.name): s.id for s in db.query(Scheme.id, Scheme.fund_family_id, Scheme.name).all()
    }
    new_schemes: dict[tuple[int, str], str] = {}  # (family_id, base_name) -> category
    for c in candidates:
        family_id = family_id_by_key[(amc_id_by_name[c.amc_name], c.amc_name)]
        key = (family_id, c.base_name)
        new_schemes.setdefault(key, c.category)
    new_schemes = {k: v for k, v in new_schemes.items() if k not in scheme_id_by_key}
    if new_schemes:
        rows = db.execute(
            insert(Scheme).returning(Scheme.id, Scheme.fund_family_id, Scheme.name),
            [
                {"fund_family_id": family_id, "name": name, "category": category}
                for (family_id, name), category in new_schemes.items()
            ],
        ).all()
        scheme_id_by_key.update({(family_id, name): scheme_id for scheme_id, family_id, name in rows})
        result.schemes_created = len(new_schemes)

    # ---- SchemeVariants ----
    variant_rows = []
    for c in candidates:
        family_id = family_id_by_key[(amc_id_by_name[c.amc_name], c.amc_name)]
        scheme_id = scheme_id_by_key[(family_id, c.base_name)]
        variant_rows.append(
            {"scheme_id": scheme_id, "plan": c.plan, "option": c.option, "amfi_code": c.scheme_code, "isin": c.isin}
        )
    if variant_rows:
        db.execute(insert(SchemeVariant), variant_rows)
        result.variants_created = len(variant_rows)

    db.commit()
    return result
