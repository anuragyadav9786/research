"""Tests for disclosure_ingestion_common's AMC-agnostic shared core:
batched ISIN/sector prefetch (fixing the original per-row N+1-SELECT
behavior) and narrow sector-name normalization (whitespace/case folding
only, never a synonym table).

Re-running ABSL's own ingestion through this shared module (rather than
ABSL's now-removed private copy of this logic) is covered by
test_absl_disclosure_ingestion.py itself -- its existing assertions pass
unmodified against the refactored absl_disclosure_ingestion.py, which is
the real proof this extraction didn't change ABSL's behavior.
"""
from datetime import date

import pytest
from sqlalchemy import event

from app.core.database import SessionLocal
from app.models.reference import AMC, FundFamily, Scheme, Sector, Security
from app.models.timeseries import PortfolioHolding, PortfolioSnapshot
from data_pipeline.normalization.disclosure_types import DisclosureHolding, DisclosureScheme
from data_pipeline.orchestration.disclosure_ingestion_common import (
    _normalize_sector_key,
    _prefetch_securities,
    _prefetch_sectors,
    ingest_amc_disclosure,
)

TEST_AMC_NAME = "Shared Infra Test Fund House"


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def test_scheme(db):
    amc = AMC(name=TEST_AMC_NAME)
    db.add(amc)
    db.flush()
    family = FundFamily(amc_id=amc.id, name=TEST_AMC_NAME)
    db.add(family)
    db.flush()
    scheme = Scheme(fund_family_id=family.id, name="Shared Infra Test Fund", category="Equity")
    db.add(scheme)
    db.commit()

    yield scheme

    db.rollback()
    db.query(PortfolioHolding).filter(
        PortfolioHolding.snapshot_id.in_(
            db.query(PortfolioSnapshot.id).filter(PortfolioSnapshot.scheme_id == scheme.id)
        )
    ).delete(synchronize_session=False)
    db.query(PortfolioSnapshot).filter(PortfolioSnapshot.scheme_id == scheme.id).delete()
    db.query(Scheme).filter(Scheme.id == scheme.id).delete()
    db.query(FundFamily).filter(FundFamily.id == family.id).delete()
    db.query(AMC).filter(AMC.id == amc.id).delete()
    db.query(Security).filter(Security.isin.like("INESHARED%")).delete(synchronize_session=False)
    db.query(Sector).filter(Sector.name.like("Shared Infra Test%")).delete(synchronize_session=False)
    db.commit()


def _equity_holding(name: str, isin: str, sector: str, weight_pct: float) -> DisclosureHolding:
    return DisclosureHolding(
        instrument_name=name, isin=isin, sector=sector, credit_rating=None, quantity=1000.0,
        market_value_rupees=500_000.0, weight_pct=weight_pct, ytm_pct=None, ytc_pct=None, instrument_type="equity",
    )


def test_prefetch_securities_issues_one_select_for_many_isins(db):
    isins = [f"INESHARED{i:06d}" for i in range(10)]
    for isin in isins:
        db.add(Security(isin=isin, name=f"Shared Infra Test Co {isin}"))
    db.commit()

    holdings = [_equity_holding(f"Co {isin}", isin, "Banks", 1.0) for isin in isins]
    holdings.append(
        DisclosureHolding(
            instrument_name="Shared Infra Test TREPS", isin=None, sector=None, credit_rating=None,
            quantity=None, market_value_rupees=1000.0, weight_pct=1.0, ytm_pct=None, ytc_pct=None,
            instrument_type="cash_equivalent",
        )
    )

    select_statements = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", _capture)
    try:
        cache = _prefetch_securities(db, holdings)
    finally:
        event.remove(db.bind, "before_cursor_execute", _capture)

    # One SELECT for the ISIN-keyed batch, one for the null-isin/name
    # batch -- not one per holding (11 holdings here).
    assert len(select_statements) == 2
    assert len(cache) == 10
    for isin in isins:
        assert cache[(isin, "")].isin == isin

    for isin in isins:
        db.query(Security).filter(Security.isin == isin).delete()
    db.commit()


def test_prefetch_then_new_insert_within_run_does_not_double_insert(db, test_scheme):
    existing_isin = "INESHARED900001"
    db.add(Security(isin=existing_isin, name="Shared Infra Pre-existing Co"))
    db.commit()

    new_isin = "INESHARED900002"
    schemes = [
        DisclosureScheme(
            short_code="SHAREDTEST",
            scheme_name="Shared Infra Test Fund",
            as_of_date=date(2026, 9, 30),
            holdings=[
                _equity_holding("Pre-existing Co", existing_isin, "Banks", 10.0),
                _equity_holding("New Co", new_isin, "IT - Software", 5.0),
                _equity_holding("New Co Again", new_isin, "IT - Software", 0.0),  # same ISIN, same run
            ],
        )
    ]

    def resolver(db, amc_name, short_code):
        return test_scheme if short_code == "SHAREDTEST" else None

    result = ingest_amc_disclosure(db, TEST_AMC_NAME, "Shared Infra Test Source", "https://example.com", schemes, resolver)

    assert result.securities_created == 1  # only the genuinely new ISIN
    new_securities = db.query(Security).filter(Security.isin == new_isin).all()
    assert len(new_securities) == 1  # never double-inserted within one run

    db.query(PortfolioHolding).filter(PortfolioHolding.snapshot_id.in_(
        db.query(PortfolioSnapshot.id).filter(PortfolioSnapshot.scheme_id == test_scheme.id)
    )).delete(synchronize_session=False)
    db.query(Security).filter(Security.isin == existing_isin).delete()
    db.query(Security).filter(Security.isin == new_isin).delete()
    db.commit()


def test_sector_normalization_folds_whitespace_and_case_not_synonyms(db):
    canonical = Sector(name="Shared Infra Test Banks")
    db.add(canonical)
    db.commit()

    cache = _prefetch_sectors(db)
    assert cache[_normalize_sector_key("shared infra test banks")].id == canonical.id
    assert cache[_normalize_sector_key("  Shared Infra Test Banks  ")].id == canonical.id
    assert cache[_normalize_sector_key("SHARED INFRA TEST BANKS")].id == canonical.id
    # A genuine wording difference is never folded into the same key.
    assert _normalize_sector_key("Shared Infra Test Banking") != _normalize_sector_key("Shared Infra Test Banks")

    db.query(Sector).filter(Sector.id == canonical.id).delete()
    db.commit()
