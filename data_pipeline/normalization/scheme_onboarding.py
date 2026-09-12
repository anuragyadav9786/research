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

Records skipped here (unparseable plan/option — most ETFs and Bonus-option
variants among them, or a missing/unrecognized category) are reported back
so the caller can log *why*, never silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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


def onboard_schemes(db: Session, raw_records: list[RawNavRecord]) -> OnboardingResult:
    result = OnboardingResult()

    known_amfi_codes = {v.amfi_code for v in db.query(SchemeVariant.amfi_code).all() if v.amfi_code}
    known_isins = {v.isin for v in db.query(SchemeVariant.isin).all() if v.isin}
    amcs_by_name: dict[str, AMC] = {a.name: a for a in db.query(AMC).all()}
    families_by_key: dict[tuple[int, str], FundFamily] = {(f.amc_id, f.name): f for f in db.query(FundFamily).all()}
    schemes_by_key: dict[tuple[int, str], Scheme] = {(s.fund_family_id, s.name): s for s in db.query(Scheme).all()}

    for rec in raw_records:
        isin = rec.isin_growth or rec.isin_div_reinvestment

        if rec.scheme_code in known_amfi_codes or (isin and isin in known_isins):
            continue  # already onboarded in a previous run (or earlier in this same file)

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

        amc = amcs_by_name.get(rec.amc_name)
        if amc is None:
            amc = AMC(name=rec.amc_name)
            db.add(amc)
            db.flush()
            amcs_by_name[amc.name] = amc
            result.amcs_created += 1

        family_key = (amc.id, amc.name)
        family = families_by_key.get(family_key)
        if family is None:
            family = FundFamily(amc_id=amc.id, name=amc.name)
            db.add(family)
            db.flush()
            families_by_key[family_key] = family
            result.fund_families_created += 1

        scheme_key = (family.id, base_name)
        scheme = schemes_by_key.get(scheme_key)
        if scheme is None:
            scheme = Scheme(fund_family_id=family.id, name=base_name, category=category)
            db.add(scheme)
            db.flush()
            schemes_by_key[scheme_key] = scheme
            result.schemes_created += 1

        db.add(
            SchemeVariant(
                scheme_id=scheme.id,
                plan=plan,
                option=option,
                amfi_code=rec.scheme_code,
                isin=isin,
            )
        )
        known_amfi_codes.add(rec.scheme_code)
        if isin:
            known_isins.add(isin)
        result.variants_created += 1

    db.commit()
    return result
