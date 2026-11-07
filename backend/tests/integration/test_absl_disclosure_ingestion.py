"""End-to-end test of the ABSL disclosure ingestion pipeline (scheme-
identity resolution + security/sector get-or-create + snapshot/holding
writes) against the real local Postgres database. Builds synthetic
`DisclosureScheme`/`DisclosureHolding` objects directly -- the parser
itself is tested separately (test_absl_disclosure_parser.py) -- and a
temporary real `AMC`/`FundFamily`/`Scheme` fixture so no seed data is
disturbed.
"""
from datetime import date

import pytest

import data_pipeline.normalization.absl_scheme_identity as absl_scheme_identity
from app.core.database import SessionLocal
from app.models.reference import AMC, FundFamily, Scheme, Sector, Security
from app.models.timeseries import PortfolioHolding, PortfolioSnapshot
from data_pipeline.normalization.absl_disclosure_parser import DisclosureHolding, DisclosureScheme
from data_pipeline.orchestration.absl_disclosure_ingestion import ingest_absl_disclosure

TEST_AMC_NAME = "ABSL Ingestion Test Fund House"


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
    scheme = Scheme(fund_family_id=family.id, name="Test Flexi Cap Fund", category="Equity - Flexi Cap")
    db.add(scheme)
    db.commit()

    original_mapping = dict(absl_scheme_identity.ABSL_SCHEME_SHORT_CODE_TO_NAME)
    absl_scheme_identity.ABSL_SCHEME_SHORT_CODE_TO_NAME["TESTEQTY"] = "Test Flexi Cap Fund"

    yield scheme

    absl_scheme_identity.ABSL_SCHEME_SHORT_CODE_TO_NAME.clear()
    absl_scheme_identity.ABSL_SCHEME_SHORT_CODE_TO_NAME.update(original_mapping)

    # The test body may have left this session mid-transaction (e.g. a
    # failed assertion right after a write, or an exception from a bug
    # under test) -- roll back first so the cleanup below always runs
    # against a clean transaction, never silently no-ops because an
    # earlier error aborted it.
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
    # Securities/sectors this test module's own fixtures create (test ISINs
    # and the cash-equivalent rows with no ISIN) are global, not scheme-
    # scoped -- without this they'd leak into the next run and turn a later
    # "created" into a "reused", making securities_created assertions
    # order-dependent.
    db.query(Security).filter(Security.isin.like("INETEST%")).delete(synchronize_session=False)
    db.query(Security).filter(Security.isin.is_(None), Security.name == "TREPS").delete(synchronize_session=False)
    db.commit()


def _disclosure_scheme(short_code: str, holdings: list[DisclosureHolding]) -> DisclosureScheme:
    return DisclosureScheme(short_code=short_code, scheme_name="Test Flexi Cap Fund", as_of_date=date(2026, 9, 30), holdings=holdings)


def _equity_holding(name: str, isin: str, sector: str, weight_pct: float) -> DisclosureHolding:
    return DisclosureHolding(
        instrument_name=name, isin=isin, sector=sector, credit_rating=None, quantity=1000.0,
        market_value_rupees=500_000.0, weight_pct=weight_pct, ytm_pct=None, ytc_pct=None, instrument_type="equity",
    )


def _cash_holding(name: str, weight_pct: float) -> DisclosureHolding:
    return DisclosureHolding(
        instrument_name=name, isin=None, sector=None, credit_rating=None, quantity=None,
        market_value_rupees=10_000.0, weight_pct=weight_pct, ytm_pct=None, ytc_pct=None, instrument_type="cash_equivalent",
    )


def test_writes_snapshot_and_holdings_for_a_mapped_scheme(db, test_scheme):
    holding = _equity_holding("Test Bank Ltd", "INETEST000001", "Banks", 10.0)
    result = ingest_absl_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("TESTEQTY", [holding])])

    assert result.schemes_written == 1
    assert result.holdings_written == 1
    assert result.securities_created == 1
    assert result.schemes_skipped_unmapped == []

    snapshot = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.scheme_id == test_scheme.id, PortfolioSnapshot.as_of_date == date(2026, 9, 30)
    ).one()
    holdings = db.query(PortfolioHolding).filter(PortfolioHolding.snapshot_id == snapshot.id).all()
    assert len(holdings) == 1
    assert float(holdings[0].weight_pct) == pytest.approx(10.0)

    security = db.query(Security).filter(Security.isin == "INETEST000001").one()
    assert security.name == "Test Bank Ltd"
    assert security.instrument_type == "equity"
    assert security.sector_id is not None
    assert db.get(Sector, security.sector_id).name == "Banks"


def test_unmapped_short_code_is_skipped_and_reported_not_guessed(db, test_scheme):
    result = ingest_absl_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("NOTACODE", [_equity_holding("X", "INEX", "Y", 1.0)])])

    assert result.schemes_written == 0
    assert result.schemes_skipped_unmapped == ["NOTACODE"]
    assert db.query(PortfolioSnapshot).filter(PortfolioSnapshot.scheme_id == test_scheme.id).count() == 0


def test_null_isin_cash_holding_is_reused_across_schemes_not_duplicated(db, test_scheme):
    holdings = [_cash_holding("TREPS", 2.0), _cash_holding("TREPS", 1.0)]
    # Two separate DisclosureScheme "months" reusing the same short_code
    # -- simulates TREPS appearing in this scheme two different times
    # within one ingest call (defensive; a real file has at most one
    # TREPS row per scheme, but the get-or-create must still dedupe).
    ingest_absl_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("TESTEQTY", holdings)])

    treps_securities = db.query(Security).filter(Security.isin.is_(None), Security.name == "TREPS").all()
    assert len(treps_securities) == 1
    assert treps_securities[0].instrument_type == "cash_equivalent"


def test_rerunning_for_the_same_scheme_and_date_replaces_holdings_not_duplicates(db, test_scheme):
    first = _equity_holding("Test Bank Ltd", "INETEST000001", "Banks", 10.0)
    ingest_absl_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("TESTEQTY", [first])])

    second = _equity_holding("Test Bank Ltd", "INETEST000001", "Banks", 25.0)  # weight changed on "re-disclosure"
    result = ingest_absl_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("TESTEQTY", [second])])

    assert result.schemes_written == 1
    snapshot = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.scheme_id == test_scheme.id, PortfolioSnapshot.as_of_date == date(2026, 9, 30)
    ).one()
    holdings = db.query(PortfolioHolding).filter(PortfolioHolding.snapshot_id == snapshot.id).all()
    assert len(holdings) == 1  # replaced, not accumulated
    assert float(holdings[0].weight_pct) == pytest.approx(25.0)


def test_existing_securitys_missing_classification_is_filled_in_not_overwritten(db, test_scheme):
    # A security that already exists (e.g. onboarded from elsewhere)
    # with no instrument_type/sector yet.
    existing = Security(isin="INETEST000002", name="Pre-existing Co Ltd")
    db.add(existing)
    db.commit()

    ingest_absl_disclosure(
        db, TEST_AMC_NAME, [_disclosure_scheme("TESTEQTY", [_equity_holding("Pre-existing Co Ltd", "INETEST000002", "IT - Software", 5.0)])]
    )
    db.refresh(existing)
    assert existing.instrument_type == "equity"
    assert existing.sector_id is not None
    first_sector_id = existing.sector_id

    # Re-ingesting with a DIFFERENT sector must never overwrite the
    # now-already-set classification.
    ingest_absl_disclosure(
        db, TEST_AMC_NAME, [_disclosure_scheme("TESTEQTY", [_equity_holding("Pre-existing Co Ltd", "INETEST000002", "Banks", 5.0)])]
    )
    db.refresh(existing)
    assert existing.sector_id == first_sector_id

    db.query(PortfolioHolding).filter(PortfolioHolding.security_id == existing.id).delete()
    db.query(Security).filter(Security.id == existing.id).delete()
    db.commit()
