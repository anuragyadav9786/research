"""Writes parsed Motilal Oswal monthly portfolio-disclosure data
(motilal_disclosure_parser.py's `DisclosureScheme`/`DisclosureHolding`)
into `portfolio_snapshots`/`portfolio_holdings`/`securities`.

Scheme identity is resolved via `motilal_scheme_identity.py`'s curated
short_code -> Scheme.name table -- a scheme not yet in that table is
reported as unmapped and its entire sheet is skipped, never guessed.

The actual get-or-create/prefetch/idempotent-snapshot-replace logic lives
in disclosure_ingestion_common.py -- shared with ABSL's own ingestion
module, not Motilal-specific. This module only supplies Motilal's own
constants and scheme resolver.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_pipeline.normalization.disclosure_types import DisclosureScheme
from data_pipeline.normalization.motilal_scheme_identity import resolve_scheme_for_short_code
from data_pipeline.orchestration.disclosure_ingestion_common import IngestionResult, ingest_amc_disclosure

DATA_SOURCE_NAME = "Motilal Oswal Monthly Portfolio Disclosure"
DATA_SOURCE_URL = "https://www.motilaloswalmf.com"


def ingest_motilal_disclosure(db: Session, amc_name: str, schemes: list[DisclosureScheme]) -> IngestionResult:
    """Writes every scheme `motilal_disclosure_parser.parse_disclosure_workbook`
    produced, for whichever ones `amc_name` + `motilal_scheme_identity`'s
    curated table can actually resolve to an onboarded `Scheme`. Commits
    once at the end -- a partial, uncommitted write on an exception
    leaves the database exactly as it was before this call, never a
    half-ingested month."""
    return ingest_amc_disclosure(
        db, amc_name, DATA_SOURCE_NAME, DATA_SOURCE_URL, schemes, resolve_scheme_for_short_code
    )
