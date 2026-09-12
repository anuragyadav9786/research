"""Map validated AMFI NAV records onto our own scheme_variants.

Design decision: this pipeline only ingests NAV for scheme_variants that
already exist in our database (matched by amfi_code, falling back to
ISIN). It never auto-creates a new AMC/fund-family/scheme/variant from a
NAV file alone — that hierarchy (Section 16-17) needs curated identity
data (AMC, category, plan/option) that NAVAll.txt's flat row doesn't
reliably carry, and inventing it from a NAV row would risk the exact kind
of fabricated/low-confidence fund-identity data Rule 2 forbids. Onboarding
a new scheme is a separate, explicit step (Phase 2-style seeding or a
future admin workflow), not a side effect of a daily NAV refresh.

Records for schemes not yet in our universe are reported as "unmapped" in
the ingestion log — visible, not silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.reference import SchemeVariant
from data_pipeline.validation.nav_validation import ValidatedNavRecord


@dataclass
class MappedNavRecord:
    scheme_variant_id: int
    record: ValidatedNavRecord


@dataclass
class MappingResult:
    matched: list[MappedNavRecord]
    unmatched: list[ValidatedNavRecord]


def map_to_scheme_variants(db: Session, records: list[ValidatedNavRecord]) -> MappingResult:
    variants = db.query(SchemeVariant).all()
    by_amfi_code = {v.amfi_code: v for v in variants if v.amfi_code}
    by_isin = {v.isin: v for v in variants if v.isin}

    matched: list[MappedNavRecord] = []
    unmatched: list[ValidatedNavRecord] = []

    for rec in records:
        variant = by_amfi_code.get(rec.scheme_code)
        if variant is None and rec.isin_growth:
            variant = by_isin.get(rec.isin_growth)
        if variant is None and rec.isin_div_reinvestment:
            variant = by_isin.get(rec.isin_div_reinvestment)

        if variant is not None:
            matched.append(MappedNavRecord(scheme_variant_id=variant.id, record=rec))
        else:
            unmatched.append(rec)

    return MappingResult(matched=matched, unmatched=unmatched)
