"""Map validated AMFI NAV records onto our own scheme_variants.

This pipeline matches NAV records to scheme_variants by amfi_code, falling
back to ISIN. As of scheme_onboarding.py, new scheme_variants ARE created
automatically from AMFI's file — conservatively, using only fields the
file itself provides, and skipping anything whose plan/option can't be
confidently parsed (see scheme_identity.py) rather than guessing at it.
Onboarding runs before this mapping step (in nav_ingestion.py), so a
scheme onboarded from today's file can still match today's NAV row.

Records that remain unmatched here — mostly ones onboarding itself
skipped, since a schemevariant that doesn't exist can't be matched by
definition — are reported as "unmapped" in the ingestion log, visible,
not silently dropped.
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
