"""Tests for benchmark_curation.py's manual category/scheme -> benchmark
mapping against the real local Postgres database. All AMC/scheme/benchmark
names below are fictional fixtures with a "Curation Test" naming prefix,
cleaned up after each test — never left in the shared dev database.
"""
from __future__ import annotations

import pytest

import data_pipeline.normalization.benchmark_curation as curation_module
from app.core.database import SessionLocal
from app.models.reference import AMC, Benchmark, FundBenchmarkHistory, FundFamily, Scheme
from data_pipeline.normalization.benchmark_curation import (
    BenchmarkSpec,
    apply_manual_benchmark_curation,
)

TEST_AMC_NAME = "Curation Test Fund House"
TEST_CATEGORY = "Curation Test - Large Cap Fund"


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def schemes(db):
    amc = AMC(name=TEST_AMC_NAME)
    db.add(amc)
    db.flush()
    family = FundFamily(amc_id=amc.id, name=TEST_AMC_NAME)
    db.add(family)
    db.flush()

    category_scheme = Scheme(fund_family_id=family.id, name="Curation Test Bluechip Fund", category=TEST_CATEGORY)
    override_scheme = Scheme(fund_family_id=family.id, name="Curation Test Special Fund", category=TEST_CATEGORY)
    already_mapped_scheme = Scheme(fund_family_id=family.id, name="Curation Test Mapped Fund", category=TEST_CATEGORY)
    unmapped_category_scheme = Scheme(fund_family_id=family.id, name="Curation Test Orphan Fund", category="Curation Test - Unmapped Category")
    db.add_all([category_scheme, override_scheme, already_mapped_scheme, unmapped_category_scheme])
    db.flush()

    existing_bm = Benchmark(name="TEST FIXTURE ALREADY-ASSIGNED INDEX")
    db.add(existing_bm)
    db.flush()
    already_mapped_scheme.benchmark_id = existing_bm.id
    db.add(
        FundBenchmarkHistory(
            scheme_id=already_mapped_scheme.id,
            benchmark_id=existing_bm.id,
            source="test_fixture_pre_existing",
        )
    )
    db.commit()

    yield {
        "category": category_scheme,
        "override": override_scheme,
        "already_mapped": already_mapped_scheme,
        "unmapped_category": unmapped_category_scheme,
    }

    db.rollback()
    scheme_ids = [s.id for s in db.query(Scheme).filter(Scheme.fund_family_id == family.id).all()]
    db.query(FundBenchmarkHistory).filter(FundBenchmarkHistory.scheme_id.in_(scheme_ids)).delete(synchronize_session=False)
    db.query(Scheme).filter(Scheme.id.in_(scheme_ids)).delete(synchronize_session=False)
    db.query(FundFamily).filter(FundFamily.id == family.id).delete(synchronize_session=False)
    db.query(AMC).filter(AMC.id == amc.id).delete(synchronize_session=False)
    created_names = ["TEST FIXTURE ALREADY-ASSIGNED INDEX", "TEST FIXTURE CATEGORY INDEX TRI", "TEST FIXTURE OVERRIDE INDEX TRI"]
    db.query(Benchmark).filter(Benchmark.name.in_(created_names)).delete(synchronize_session=False)
    db.commit()


@pytest.fixture(autouse=True)
def _clear_curation_maps():
    """CATEGORY_BENCHMARK_MAP/SCHEME_BENCHMARK_OVERRIDES are meant to hold
    real, sourced entries in production — never left populated with test
    fixtures once a test finishes."""
    yield
    curation_module.CATEGORY_BENCHMARK_MAP.clear()
    curation_module.SCHEME_BENCHMARK_OVERRIDES.clear()


def test_assigns_category_default_and_creates_benchmark(db, schemes):
    curation_module.CATEGORY_BENCHMARK_MAP[TEST_CATEGORY] = BenchmarkSpec(
        name="TEST FIXTURE CATEGORY INDEX TRI",
        provider="NSE",
        symbol="TEST FIXTURE CATEGORY INDEX",
        benchmark_type="TRI",
    )

    result = apply_manual_benchmark_curation(db)

    db.refresh(schemes["category"])
    assert schemes["category"].benchmark_id is not None
    bm = db.get(Benchmark, schemes["category"].benchmark_id)
    assert bm.name == "TEST FIXTURE CATEGORY INDEX TRI"
    assert bm.provider == "NSE"
    assert result.benchmarks_created == 1
    assert "Curation Test Bluechip Fund" in result.assigned_scheme_names


def test_scheme_override_takes_priority_over_category_default(db, schemes):
    curation_module.CATEGORY_BENCHMARK_MAP[TEST_CATEGORY] = BenchmarkSpec(name="TEST FIXTURE CATEGORY INDEX TRI")
    curation_module.SCHEME_BENCHMARK_OVERRIDES["Curation Test Special Fund"] = BenchmarkSpec(
        name="TEST FIXTURE OVERRIDE INDEX TRI"
    )

    apply_manual_benchmark_curation(db)

    db.refresh(schemes["override"])
    bm = db.get(Benchmark, schemes["override"].benchmark_id)
    assert bm.name == "TEST FIXTURE OVERRIDE INDEX TRI"


def test_never_overwrites_an_already_mapped_scheme(db, schemes):
    curation_module.CATEGORY_BENCHMARK_MAP[TEST_CATEGORY] = BenchmarkSpec(name="TEST FIXTURE CATEGORY INDEX TRI")
    original_benchmark_id = schemes["already_mapped"].benchmark_id

    result = apply_manual_benchmark_curation(db)

    db.refresh(schemes["already_mapped"])
    assert schemes["already_mapped"].benchmark_id == original_benchmark_id
    assert "Curation Test Mapped Fund" not in result.assigned_scheme_names


def test_scheme_with_no_matching_category_is_skipped_not_guessed(db, schemes):
    curation_module.CATEGORY_BENCHMARK_MAP[TEST_CATEGORY] = BenchmarkSpec(name="TEST FIXTURE CATEGORY INDEX TRI")

    result = apply_manual_benchmark_curation(db)

    db.refresh(schemes["unmapped_category"])
    assert schemes["unmapped_category"].benchmark_id is None
    assert result.schemes_skipped_no_mapping >= 1
    assert "Curation Test Orphan Fund" not in result.assigned_scheme_names


def test_empty_maps_are_a_no_op(db, schemes):
    result = apply_manual_benchmark_curation(db)

    assert result.schemes_assigned == 0
    assert result.benchmarks_created == 0
    db.refresh(schemes["category"])
    assert schemes["category"].benchmark_id is None
