"""Writes parsed ABSL monthly portfolio-disclosure data
(absl_disclosure_parser.py's `DisclosureScheme`/`DisclosureHolding`)
into `portfolio_snapshots`/`portfolio_holdings`/`securities` -- the
ingestion half of the pipeline `portfolio-fetcher/README.md` promises
but that, until now, didn't exist anywhere in this repo (confirmed:
`portfolio-fetcher/` only uploads the raw file to Google Drive).

Scheme identity is resolved via `absl_scheme_identity.py`'s curated
short_code -> Scheme.name table -- a scheme not yet in that table is
reported as unmapped and its entire sheet is skipped, never guessed.

The actual get-or-create/prefetch/idempotent-snapshot-replace logic lives
in disclosure_ingestion_common.py -- shared with every other AMC's
ingestion module, not ABSL-specific. This module only supplies ABSL's own
constants and scheme resolver.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_pipeline.normalization.absl_disclosure_parser import DisclosureScheme
from data_pipeline.normalization.absl_scheme_identity import resolve_scheme_for_short_code
from data_pipeline.orchestration.disclosure_ingestion_common import IngestionResult, ingest_amc_disclosure

DATA_SOURCE_NAME = "ABSL Monthly Portfolio Disclosure"
DATA_SOURCE_URL = "https://mutualfund.adityabirlacapital.com"


def ingest_absl_disclosure(db: Session, amc_name: str, schemes: list[DisclosureScheme]) -> IngestionResult:
    """Writes every scheme `absl_disclosure_parser.parse_disclosure_workbook`
    produced, for whichever ones `amc_name` + `absl_scheme_identity`'s
    curated table can actually resolve to an onboarded `Scheme`. Commits
    once at the end -- a partial, uncommitted write on an exception
    leaves the database exactly as it was before this call, never a
    half-ingested month."""
    return ingest_amc_disclosure(
        db, amc_name, DATA_SOURCE_NAME, DATA_SOURCE_URL, schemes, resolve_scheme_for_short_code
    )
