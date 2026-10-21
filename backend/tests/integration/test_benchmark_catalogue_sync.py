"""Integration tests for the AMFI-driven benchmark catalogue sync, against
the real local Postgres database with Phase 2 seed data loaded (see
seed_sample_data.py — "Northbridge Bluechip Equity Fund" etc.). The
network fetch (fetch_subcategories / fetch_scheme_performance) is
monkeypatched — confirmed working against the real live AMFI gateway
earlier this session, not re-exercised on every test run.
"""
from datetime import date

import pytest

import data_pipeline.orchestration.benchmark_catalogue_sync as sync_module
from app.core.database import SessionLocal
from app.models.reference import Benchmark, Scheme
from data_pipeline.orchestration.benchmark_catalogue_sync import (
    _benchmark_type_for,
    _normalize,
    _provider_for,
    run_benchmark_catalogue_sync,
)
from data_pipeline.sources.amfi.fund_performance import SchemePerformanceRow, SubCategory

BLUECHIP_SCHEME_NAME = "Northbridge Bluechip Equity Fund"
FLEXICAP_SCHEME_NAME = "Northbridge Flexi Cap Fund"
TEST_BENCHMARK_NAME = "Nifty 100 TRI (Catalogue Sync Test)"


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def restore_scheme_state(db):
    schemes = db.query(Scheme).filter(Scheme.name.in_([BLUECHIP_SCHEME_NAME, FLEXICAP_SCHEME_NAME])).all()
    original = {s.id: s.benchmark_id for s in schemes}
    yield
    # Restore the FK reference FIRST -- only once nothing points at a test
    # benchmark row can it be deleted without violating schemes_benchmark_id_fkey.
    for scheme_id, benchmark_id in original.items():
        db.get(Scheme, scheme_id).benchmark_id = benchmark_id
    db.commit()
    db.query(Benchmark).filter(Benchmark.name.ilike("%Catalogue Sync Test%")).delete(synchronize_session=False)
    db.commit()


def test_provider_and_type_inference():
    assert _provider_for("Nifty 100 TRI") == "NSE"
    assert _provider_for("NIFTY MIDCAP 150 TRI") == "NSE"
    assert _provider_for("BSE 100 TRI") == "BSE"
    assert _provider_for("S&P BSE 500 TRI") == "BSE"
    assert _provider_for("Some Unknown Index") is None

    assert _benchmark_type_for("Nifty 100 TRI") == "TRI"
    assert _benchmark_type_for("Nifty 100") == "PRICE"


def test_normalize_collapses_case_and_whitespace():
    assert _normalize("  Northbridge   Bluechip Equity Fund ") == _normalize("northbridge bluechip equity fund")


def test_sync_matches_real_scheme_creates_benchmark_and_sets_benchmark_id(db, restore_scheme_state, monkeypatch):
    monkeypatch.setattr(
        sync_module, "fetch_subcategories", lambda investment_type: [SubCategory(id=1, name="Large Cap")]
    )
    monkeypatch.setattr(
        sync_module,
        "fetch_scheme_performance",
        lambda investment_type, sub_category_id, report_date: [
            SchemePerformanceRow(scheme_name=BLUECHIP_SCHEME_NAME, benchmark=TEST_BENCHMARK_NAME),
            SchemePerformanceRow(scheme_name="A Totally Unknown Fund Not In Our DB", benchmark="Nifty 500 TRI"),
        ],
    )

    result = run_benchmark_catalogue_sync(db, report_date=date(2026, 10, 19))

    assert result.schemes_seen == 2
    assert result.schemes_matched == 1
    assert "A Totally Unknown Fund Not In Our DB" in result.schemes_unmatched
    assert result.benchmarks_created == 1
    assert result.distinct_benchmarks_assigned == {TEST_BENCHMARK_NAME: "NSE"}

    scheme = db.query(Scheme).filter(Scheme.name == BLUECHIP_SCHEME_NAME).first()
    db.refresh(scheme)
    assert scheme.benchmark_id is not None
    benchmark = db.get(Benchmark, scheme.benchmark_id)
    assert benchmark.name == TEST_BENCHMARK_NAME
    assert benchmark.provider == "NSE"
    assert benchmark.benchmark_type == "TRI"


def test_sync_is_idempotent_no_duplicate_benchmark_rows(db, restore_scheme_state, monkeypatch):
    monkeypatch.setattr(
        sync_module, "fetch_subcategories", lambda investment_type: [SubCategory(id=1, name="Large Cap")]
    )
    monkeypatch.setattr(
        sync_module,
        "fetch_scheme_performance",
        lambda investment_type, sub_category_id, report_date: [
            SchemePerformanceRow(scheme_name=BLUECHIP_SCHEME_NAME, benchmark=TEST_BENCHMARK_NAME),
        ],
    )

    run_benchmark_catalogue_sync(db, report_date=date(2026, 10, 19))
    run_benchmark_catalogue_sync(db, report_date=date(2026, 10, 20))  # re-run, same benchmark name

    count = db.query(Benchmark).filter(Benchmark.name == TEST_BENCHMARK_NAME).count()
    assert count == 1


def test_sync_reassigns_benchmark_if_amfi_disclosed_one_changes(db, restore_scheme_state, monkeypatch):
    """A scheme's real-world benchmark can change (a genuine
    re-benchmarking event) -- the sync should follow AMFI's current
    disclosure, not keep whatever was assigned on a previous run."""
    monkeypatch.setattr(
        sync_module, "fetch_subcategories", lambda investment_type: [SubCategory(id=1, name="Large Cap")]
    )
    monkeypatch.setattr(
        sync_module,
        "fetch_scheme_performance",
        lambda investment_type, sub_category_id, report_date: [
            SchemePerformanceRow(scheme_name=BLUECHIP_SCHEME_NAME, benchmark=TEST_BENCHMARK_NAME),
        ],
    )
    run_benchmark_catalogue_sync(db, report_date=date(2026, 10, 19))
    scheme = db.query(Scheme).filter(Scheme.name == BLUECHIP_SCHEME_NAME).first()
    first_benchmark_id = scheme.benchmark_id

    new_benchmark_name = "Nifty 50 TRI (Catalogue Sync Test Reassignment)"
    monkeypatch.setattr(
        sync_module,
        "fetch_scheme_performance",
        lambda investment_type, sub_category_id, report_date: [
            SchemePerformanceRow(scheme_name=BLUECHIP_SCHEME_NAME, benchmark=new_benchmark_name),
        ],
    )
    run_benchmark_catalogue_sync(db, report_date=date(2026, 10, 21))
    db.refresh(scheme)
    assert scheme.benchmark_id != first_benchmark_id
    assert db.get(Benchmark, scheme.benchmark_id).name == new_benchmark_name
