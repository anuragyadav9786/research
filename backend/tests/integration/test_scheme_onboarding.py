"""Integration tests for onboard_schemes against the real local Postgres
database. All AMC/scheme names and codes below are fictional fixtures with
an "Onboarding Test" naming prefix distinct from both real data and the
Phase 2 sample seed data — used only so this test's rows can be found and
cleaned up precisely, never left behind in the shared dev database.
"""
import pytest

from app.core.database import SessionLocal
from app.models.reference import AMC, FundFamily, Scheme, SchemeVariant
from data_pipeline.normalization.scheme_onboarding import onboard_schemes
from data_pipeline.sources.amfi.parser import parse_navall

TEST_AMC_NAME = "Onboarding Test Fund House"

FIXTURE_TEXT = (
    "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n\n"
    "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n\n"
    f"{TEST_AMC_NAME}\n"
    "ONB700001;ONB-ISIN-01;-;Onboarding Test Bluechip Fund - Direct Plan - Growth;123.4567;12-Sep-2026\n"
    "ONB700002;ONB-ISIN-02;-;Onboarding Test Bluechip Fund - Regular Plan - Growth;120.1234;12-Sep-2026\n"
    "ONB700003;-;-;Onboarding Test Nifty 50 ETF;250.0000;12-Sep-2026\n"
)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def _cleanup(db) -> None:
    amcs = db.query(AMC).filter(AMC.name == TEST_AMC_NAME).all()
    amc_ids = [a.id for a in amcs]
    families = db.query(FundFamily).filter(FundFamily.amc_id.in_(amc_ids)).all()
    family_ids = [f.id for f in families]
    schemes = db.query(Scheme).filter(Scheme.fund_family_id.in_(family_ids)).all()
    scheme_ids = [s.id for s in schemes]
    db.query(SchemeVariant).filter(SchemeVariant.scheme_id.in_(scheme_ids)).delete(synchronize_session=False)
    db.query(Scheme).filter(Scheme.id.in_(scheme_ids)).delete(synchronize_session=False)
    db.query(FundFamily).filter(FundFamily.id.in_(family_ids)).delete(synchronize_session=False)
    db.query(AMC).filter(AMC.id.in_(amc_ids)).delete(synchronize_session=False)
    db.commit()


def test_onboards_amc_family_scheme_and_variants(db):
    raw_records = parse_navall(FIXTURE_TEXT)
    try:
        result = onboard_schemes(db, raw_records)

        assert result.amcs_created == 1
        assert result.fund_families_created == 1
        assert result.schemes_created == 1  # both Direct/Regular rows share one base scheme
        assert result.variants_created == 2
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == "could not determine plan/option from scheme name"
        assert result.skipped[0].scheme_code == "ONB700003"

        amc = db.query(AMC).filter(AMC.name == TEST_AMC_NAME).one()
        family = db.query(FundFamily).filter(FundFamily.amc_id == amc.id).one()
        assert family.name == TEST_AMC_NAME  # mirrors AMC name — see module docstring

        scheme = db.query(Scheme).filter(Scheme.fund_family_id == family.id).one()
        assert scheme.name == "Onboarding Test Bluechip Fund"
        assert scheme.category == "Equity Scheme - Large Cap Fund"

        variants = db.query(SchemeVariant).filter(SchemeVariant.scheme_id == scheme.id).all()
        assert {v.plan for v in variants} == {"direct", "regular"}
        assert {v.option for v in variants} == {"growth"}
        assert {v.amfi_code for v in variants} == {"ONB700001", "ONB700002"}
    finally:
        _cleanup(db)


def test_rerunning_onboarding_is_idempotent(db):
    raw_records = parse_navall(FIXTURE_TEXT)
    try:
        first = onboard_schemes(db, raw_records)
        second = onboard_schemes(db, raw_records)

        assert first.variants_created == 2
        assert second.variants_created == 0  # already onboarded — matched by amfi_code, not recreated

        variant_count = (
            db.query(SchemeVariant)
            .filter(SchemeVariant.amfi_code.in_(["ONB700001", "ONB700002"]))
            .count()
        )
        assert variant_count == 2  # no duplicates from the second run
    finally:
        _cleanup(db)
