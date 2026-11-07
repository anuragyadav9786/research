"""End-to-end test of the Motilal Oswal disclosure ingestion pipeline
(scheme-identity resolution + security/sector get-or-create + snapshot/
holding writes, via the shared disclosure_ingestion_common module)
against the real local Postgres database. Mirrors
test_absl_disclosure_ingestion.py's structure exactly -- same shared
ingestion path, different AMC's scheme-identity module.
"""
from datetime import date

import pytest

import data_pipeline.normalization.motilal_scheme_identity as motilal_scheme_identity
from app.core.database import SessionLocal
from app.models.reference import AMC, FundFamily, Scheme, Sector, Security
from app.models.timeseries import PortfolioHolding, PortfolioSnapshot
from data_pipeline.normalization.disclosure_types import DisclosureHolding, DisclosureScheme
from data_pipeline.orchestration.motilal_disclosure_ingestion import ingest_motilal_disclosure

TEST_AMC_NAME = "Motilal Ingestion Test Fund House"


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
    scheme = Scheme(fund_family_id=family.id, name="Test Motilal Flexi Cap Fund", category="Equity - Flexi Cap")
    db.add(scheme)
    db.commit()

    original_mapping = dict(motilal_scheme_identity.MOTILAL_SCHEME_SHORT_CODE_TO_NAME)
    motilal_scheme_identity.MOTILAL_SCHEME_SHORT_CODE_TO_NAME["YOTEST"] = "Test Motilal Flexi Cap Fund"

    yield scheme

    motilal_scheme_identity.MOTILAL_SCHEME_SHORT_CODE_TO_NAME.clear()
    motilal_scheme_identity.MOTILAL_SCHEME_SHORT_CODE_TO_NAME.update(original_mapping)

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
    db.query(Security).filter(Security.isin.like("INEMOTEST%")).delete(synchronize_session=False)
    db.query(Security).filter(
        Security.isin.is_(None), Security.name == "Triparty Repo"
    ).delete(synchronize_session=False)
    db.commit()


def _disclosure_scheme(short_code: str, holdings: list[DisclosureHolding]) -> DisclosureScheme:
    return DisclosureScheme(
        short_code=short_code, scheme_name="Test Motilal Flexi Cap Fund", as_of_date=date(2026, 9, 30), holdings=holdings
    )


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
    holding = _equity_holding("Test Bank Ltd", "INEMOTEST000001", "Banks", 10.0)
    result = ingest_motilal_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("YOTEST", [holding])])

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

    security = db.query(Security).filter(Security.isin == "INEMOTEST000001").one()
    assert security.name == "Test Bank Ltd"
    assert security.instrument_type == "equity"
    assert security.sector_id is not None
    assert db.get(Sector, security.sector_id).name == "Banks"


def test_unmapped_short_code_is_skipped_and_reported_not_guessed(db, test_scheme):
    result = ingest_motilal_disclosure(
        db, TEST_AMC_NAME, [_disclosure_scheme("NOTACODE", [_equity_holding("X", "INEX", "Y", 1.0)])]
    )

    assert result.schemes_written == 0
    assert result.schemes_skipped_unmapped == ["NOTACODE"]
    assert db.query(PortfolioSnapshot).filter(PortfolioSnapshot.scheme_id == test_scheme.id).count() == 0


def test_null_isin_cash_holding_is_reused_across_schemes_not_duplicated(db, test_scheme):
    holdings = [_cash_holding("Triparty Repo", 2.0), _cash_holding("Triparty Repo", 1.0)]
    ingest_motilal_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("YOTEST", holdings)])

    repo_securities = db.query(Security).filter(Security.isin.is_(None), Security.name == "Triparty Repo").all()
    assert len(repo_securities) == 1
    assert repo_securities[0].instrument_type == "cash_equivalent"


def test_rerunning_for_the_same_scheme_and_date_replaces_holdings_not_duplicates(db, test_scheme):
    first = _equity_holding("Test Bank Ltd", "INEMOTEST000001", "Banks", 10.0)
    ingest_motilal_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("YOTEST", [first])])

    second = _equity_holding("Test Bank Ltd", "INEMOTEST000001", "Banks", 25.0)
    result = ingest_motilal_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("YOTEST", [second])])

    assert result.schemes_written == 1
    snapshot = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.scheme_id == test_scheme.id, PortfolioSnapshot.as_of_date == date(2026, 9, 30)
    ).one()
    holdings = db.query(PortfolioHolding).filter(PortfolioHolding.snapshot_id == snapshot.id).all()
    assert len(holdings) == 1
    assert float(holdings[0].weight_pct) == pytest.approx(25.0)


def test_existing_securitys_missing_classification_is_filled_in_not_overwritten(db, test_scheme):
    existing = Security(isin="INEMOTEST000002", name="Pre-existing Co Ltd")
    db.add(existing)
    db.commit()

    ingest_motilal_disclosure(
        db, TEST_AMC_NAME,
        [_disclosure_scheme("YOTEST", [_equity_holding("Pre-existing Co Ltd", "INEMOTEST000002", "IT - Software", 5.0)])],
    )
    db.refresh(existing)
    assert existing.instrument_type == "equity"
    assert existing.sector_id is not None
    first_sector_id = existing.sector_id

    ingest_motilal_disclosure(
        db, TEST_AMC_NAME,
        [_disclosure_scheme("YOTEST", [_equity_holding("Pre-existing Co Ltd", "INEMOTEST000002", "Banks", 5.0)])],
    )
    db.refresh(existing)
    assert existing.sector_id == first_sector_id

    db.query(PortfolioHolding).filter(PortfolioHolding.security_id == existing.id).delete()
    db.query(Security).filter(Security.id == existing.id).delete()
    db.commit()


def test_negative_weight_derivatives_holding_is_stored_without_fabricating_an_isin(db, test_scheme):
    future_holding = DisclosureHolding(
        instrument_name="Some Co Ltd October 2026 Future", isin=None, sector=None, credit_rating=None,
        quantity=-450.0, market_value_rupees=-1_985_000.0, weight_pct=-0.01, ytm_pct=None, ytc_pct=None,
        instrument_type="other",
    )
    result = ingest_motilal_disclosure(db, TEST_AMC_NAME, [_disclosure_scheme("YOTEST", [future_holding])])

    assert result.holdings_written == 1
    snapshot = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.scheme_id == test_scheme.id, PortfolioSnapshot.as_of_date == date(2026, 9, 30)
    ).one()
    holding = db.query(PortfolioHolding).filter(PortfolioHolding.snapshot_id == snapshot.id).one()
    assert float(holding.weight_pct) == pytest.approx(-0.01)
    assert float(holding.quantity) == pytest.approx(-450.0)

    db.query(PortfolioHolding).filter(PortfolioHolding.snapshot_id == snapshot.id).delete()
    db.query(Security).filter(
        Security.isin.is_(None), Security.name == "Some Co Ltd October 2026 Future"
    ).delete(synchronize_session=False)
    db.commit()
