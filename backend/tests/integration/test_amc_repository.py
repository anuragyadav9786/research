"""Integration tests for amc_repository.py against the real local
Postgres database -- explicit fixture AMC/FundFamily/Scheme rows and
teardown, same discipline as test_motilal_disclosure_ingestion.py.
"""
from datetime import date

import pytest

from app.core.database import SessionLocal
from app.models.reference import AMC, FundFamily, Scheme
from app.models.timeseries import DataSource, PortfolioSnapshot
from app.repositories import amc_repository

TEST_AMC_NAME = "AMC Repository Test Fund House"


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def amc_with_schemes(db):
    amc = AMC(name=TEST_AMC_NAME)
    db.add(amc)
    db.flush()
    family = FundFamily(amc_id=amc.id, name=TEST_AMC_NAME)
    db.add(family)
    db.flush()

    scheme_with_holdings = Scheme(fund_family_id=family.id, name="Test Fund A", category="Equity")
    scheme_without_holdings = Scheme(fund_family_id=family.id, name="Test Fund B", category="Debt")
    db.add_all([scheme_with_holdings, scheme_without_holdings])
    db.flush()

    source = DataSource(name="AMC Repository Test Source", url="https://example.com", source_type="amc")
    db.add(source)
    db.flush()
    snapshot = PortfolioSnapshot(scheme_id=scheme_with_holdings.id, as_of_date=date(2026, 9, 30), source_id=source.id)
    db.add(snapshot)
    db.commit()

    yield amc, scheme_with_holdings, scheme_without_holdings

    db.rollback()
    db.query(PortfolioSnapshot).filter(PortfolioSnapshot.scheme_id == scheme_with_holdings.id).delete()
    db.query(DataSource).filter(DataSource.id == source.id).delete()
    db.query(Scheme).filter(Scheme.fund_family_id == family.id).delete()
    db.query(FundFamily).filter(FundFamily.id == family.id).delete()
    db.query(AMC).filter(AMC.id == amc.id).delete()
    db.commit()


def test_list_amcs_includes_new_amc_with_correct_counts(db, amc_with_schemes):
    amc, _, _ = amc_with_schemes
    rows = amc_repository.list_amcs(db)
    row = next(r for r in rows if r.id == amc.id)
    assert row.name == TEST_AMC_NAME
    assert row.fund_family_count == 1
    assert row.scheme_count == 2
    # Only one of the two schemes has a PortfolioSnapshot.
    assert row.schemes_with_holdings_count == 1


def test_get_amc_returns_none_for_unknown_id(db):
    assert amc_repository.get_amc(db, 999_999_999) is None


def test_get_amc_returns_the_amc(db, amc_with_schemes):
    amc, _, _ = amc_with_schemes
    found = amc_repository.get_amc(db, amc.id)
    assert found is not None
    assert found.name == TEST_AMC_NAME


def test_list_schemes_for_amc_reports_holdings_date_only_where_present(db, amc_with_schemes):
    amc, scheme_with_holdings, scheme_without_holdings = amc_with_schemes
    rows = amc_repository.list_schemes_for_amc(db, amc.id)
    by_id = {r.id: r for r in rows}

    assert by_id[scheme_with_holdings.id].holdings_as_of_date == date(2026, 9, 30)
    assert by_id[scheme_without_holdings.id].holdings_as_of_date is None
    assert all(r.fund_family_name == TEST_AMC_NAME for r in rows)


def test_list_schemes_for_amc_empty_for_unknown_amc(db):
    assert amc_repository.list_schemes_for_amc(db, 999_999_999) == []
