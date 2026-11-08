"""Integration tests for security_repository.py against the real local
Postgres database -- explicit fixtures, same discipline as
test_amc_repository.py / test_motilal_disclosure_ingestion.py.

The scenario this feature exists for: one real security held by schemes
under two UNRELATED AMCs. Built explicitly here (rather than assumed)
since local dev Postgres doesn't carry the real ABSL/Motilal production
data this session loaded.
"""
from datetime import date

import pytest

from app.core.database import SessionLocal
from app.models.reference import AMC, FundFamily, Scheme, Security
from app.models.timeseries import DataSource, PortfolioHolding, PortfolioSnapshot
from app.repositories import security_repository

TEST_SECURITY_ISIN = "INETESTCROSSAMC1"


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def shared_security_across_two_amcs(db):
    security = Security(isin=TEST_SECURITY_ISIN, name="Cross-AMC Test Holding Ltd", instrument_type="equity")
    db.add(security)
    db.flush()

    source = DataSource(name="Security Repository Test Source", url="https://example.com", source_type="amc")
    db.add(source)
    db.flush()

    amc_a = AMC(name="Security Repository Test AMC A")
    amc_b = AMC(name="Security Repository Test AMC B")
    db.add_all([amc_a, amc_b])
    db.flush()
    family_a = FundFamily(amc_id=amc_a.id, name="Security Repository Test AMC A")
    family_b = FundFamily(amc_id=amc_b.id, name="Security Repository Test AMC B")
    db.add_all([family_a, family_b])
    db.flush()
    scheme_a = Scheme(fund_family_id=family_a.id, name="Test Fund (AMC A)", category="Equity")
    scheme_b = Scheme(fund_family_id=family_b.id, name="Test Fund (AMC B)", category="Equity")
    db.add_all([scheme_a, scheme_b])
    db.flush()

    snapshot_a = PortfolioSnapshot(scheme_id=scheme_a.id, as_of_date=date(2026, 9, 30), source_id=source.id)
    snapshot_b = PortfolioSnapshot(scheme_id=scheme_b.id, as_of_date=date(2026, 9, 30), source_id=source.id)
    db.add_all([snapshot_a, snapshot_b])
    db.flush()

    db.add_all(
        [
            PortfolioHolding(snapshot_id=snapshot_a.id, security_id=security.id, weight_pct=4.5, market_value=1000.0),
            PortfolioHolding(snapshot_id=snapshot_b.id, security_id=security.id, weight_pct=2.1, market_value=500.0),
        ]
    )
    db.commit()

    yield security, scheme_a, scheme_b, amc_a, amc_b

    db.rollback()
    db.query(PortfolioHolding).filter(PortfolioHolding.security_id == security.id).delete()
    db.query(PortfolioSnapshot).filter(PortfolioSnapshot.id.in_([snapshot_a.id, snapshot_b.id])).delete()
    db.query(Scheme).filter(Scheme.id.in_([scheme_a.id, scheme_b.id])).delete()
    db.query(FundFamily).filter(FundFamily.id.in_([family_a.id, family_b.id])).delete()
    db.query(AMC).filter(AMC.id.in_([amc_a.id, amc_b.id])).delete()
    db.query(DataSource).filter(DataSource.id == source.id).delete()
    db.query(Security).filter(Security.id == security.id).delete()
    db.commit()


def test_search_securities_finds_by_isin_substring(db, shared_security_across_two_amcs):
    security, *_ = shared_security_across_two_amcs
    results = security_repository.search_securities(db, "TESTCROSSAMC1")
    assert any(s.id == security.id for s in results)


def test_search_securities_finds_by_name_substring(db, shared_security_across_two_amcs):
    security, *_ = shared_security_across_two_amcs
    results = security_repository.search_securities(db, "Cross-AMC Test")
    assert any(s.id == security.id for s in results)


def test_get_security_returns_none_for_unknown_id(db):
    assert security_repository.get_security(db, 999_999_999) is None


def test_get_holders_returns_both_schemes_across_both_amcs(db, shared_security_across_two_amcs):
    security, scheme_a, scheme_b, amc_a, amc_b = shared_security_across_two_amcs
    holders = security_repository.get_holders(db, security.id)

    assert len(holders) == 2
    by_scheme = {h.scheme_id: h for h in holders}
    assert by_scheme[scheme_a.id].amc_name == amc_a.name
    assert by_scheme[scheme_a.id].weight_pct == pytest.approx(4.5)
    assert by_scheme[scheme_b.id].amc_name == amc_b.name
    assert by_scheme[scheme_b.id].weight_pct == pytest.approx(2.1)

    # Highest weight first.
    assert holders[0].scheme_id == scheme_a.id


def test_get_holders_only_counts_each_schemes_latest_snapshot(db, shared_security_across_two_amcs):
    security, scheme_a, scheme_b, amc_a, amc_b = shared_security_across_two_amcs

    # Add an earlier (now-stale) snapshot for scheme A that no longer
    # holds this security -- the holder list must not double-count it or
    # fall back to the stale weight.
    source = db.query(DataSource).filter(DataSource.name == "Security Repository Test Source").one()
    older_snapshot = PortfolioSnapshot(scheme_id=scheme_a.id, as_of_date=date(2026, 8, 31), source_id=source.id)
    db.add(older_snapshot)
    db.flush()
    db.add(PortfolioHolding(snapshot_id=older_snapshot.id, security_id=security.id, weight_pct=99.0))
    db.commit()

    holders = security_repository.get_holders(db, security.id)
    by_scheme = {h.scheme_id: h for h in holders}
    assert len(holders) == 2
    assert by_scheme[scheme_a.id].weight_pct == pytest.approx(4.5)
    assert by_scheme[scheme_a.id].as_of_date == date(2026, 9, 30)

    db.query(PortfolioHolding).filter(PortfolioHolding.snapshot_id == older_snapshot.id).delete()
    db.query(PortfolioSnapshot).filter(PortfolioSnapshot.id == older_snapshot.id).delete()
    db.commit()


def test_get_holders_empty_for_security_nobody_holds(db):
    assert security_repository.get_holders(db, 999_999_999) == []
