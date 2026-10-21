"""End-to-end test of the fund screener's daily rollup against the real
local Postgres database (Phase 2 seed data must be loaded — see
seed_sample_data.py: 4 schemes x {regular, direct} plans, option=growth
always, 3 equity + 1 debt, each with a distinct amfi_code "SMP<code>R/D<n>").
The network fetch is monkeypatched — this sandbox's outbound access to
portal.amfiindia.com, while confirmed working earlier this session, isn't
exercised on every test run — but eligibility filtering, anchor-date
math, return computation, and the real upsert-with-overwrite write all
run for real against Postgres.
"""
from datetime import date

import pytest

import data_pipeline.orchestration.period_return_rollup as rollup_module
from app.core.database import SessionLocal
from app.models.reference import Scheme, SchemeVariant
from app.models.timeseries import FundPeriodReturn
from data_pipeline.orchestration.period_return_rollup import (
    PERIODS,
    _eligible_variants,
    _fetch_with_fallback,
    _months_before,
    run_period_return_rollup,
)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def seeded_variants(db):
    variants = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.like("SMP%")).all()
    assert variants, "requires Phase 2 seed data to be loaded"
    yield variants
    ids = [v.id for v in variants]
    db.query(FundPeriodReturn).filter(FundPeriodReturn.scheme_variant_id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def test_months_before_handles_month_length_and_leap_years():
    assert _months_before(date(2026, 10, 20), 1) == date(2026, 9, 20)
    assert _months_before(date(2026, 10, 20), 12) == date(2025, 10, 20)
    # 31-Oct minus 1 month -> clamped to Sep's real last day (30), not an
    # invalid "31-Sep".
    assert _months_before(date(2026, 10, 31), 1) == date(2026, 9, 30)
    # 31-Mar-2024 minus 1 month -> Feb 2024 is a leap year, real last day 29.
    assert _months_before(date(2024, 3, 31), 1) == date(2024, 2, 29)


def test_eligible_variants_excludes_direct_plan_and_schemes_with_no_benchmark(seeded_variants, db):
    """Real production never sets Scheme.benchmark_id automatically except
    via benchmark_catalogue_sync.py (AMFI's own confirmed Equity
    classification) — so this test controls benchmark_id directly, rather
    than relying on seed_sample_data.py's synthetic assignments (which
    set a benchmark_id on its debt scheme too, for unrelated analytics
    test purposes)."""
    scheme_ids = {v.scheme_id for v in seeded_variants}
    original_benchmark_ids = {
        s.id: s.benchmark_id for s in db.query(Scheme).filter(Scheme.id.in_(scheme_ids))
    }
    debt_scheme_ids = {s.id for s in db.query(Scheme).filter(Scheme.category.ilike("Debt%"))}
    equity_scheme_ids = scheme_ids - debt_scheme_ids
    assert equity_scheme_ids, "expected at least one non-debt seeded scheme"

    try:
        # Simulate the real post-sync state: equity schemes have a
        # confirmed benchmark, the debt scheme never got one.
        for scheme_id, original in original_benchmark_ids.items():
            scheme = db.get(Scheme, scheme_id)
            scheme.benchmark_id = original if scheme_id in equity_scheme_ids else None
        db.commit()

        eligible = _eligible_variants(db)

        regular_codes = {v.amfi_code for v in seeded_variants if v.plan == "regular" and v.scheme_id in equity_scheme_ids}
        direct_codes = {v.amfi_code for v in seeded_variants if v.plan == "direct"}
        debt_codes = {v.amfi_code for v in seeded_variants if v.scheme_id in debt_scheme_ids}

        # Every regular-plan, confirmed-benchmark seeded code is present...
        assert regular_codes <= eligible.keys()
        # ...and no direct-plan or no-benchmark (debt) seeded code leaked in.
        assert not (direct_codes & eligible.keys())
        assert not (debt_codes & eligible.keys())
    finally:
        for scheme_id, original in original_benchmark_ids.items():
            db.get(Scheme, scheme_id).benchmark_id = original
        db.commit()


def test_rollup_computes_real_returns_and_overwrites_on_rerun(seeded_variants, db, monkeypatch):
    today = date(2026, 10, 20)
    # One regular+growth, non-debt seeded variant to track through the run.
    tracked = next(v for v in seeded_variants if v.plan == "regular" and not v.scheme.category.lower().startswith("debt"))

    all_eligible_codes = _eligible_variants(db).keys()

    # today = 100, every anchor date = 80 -> every period's return is +25%
    # for every eligible scheme, so the full "every eligible x every
    # period" count below is meaningful.
    def _fake_fetch(target_date: date):
        value = 100.0 if target_date == today else 80.0
        navs = {code: value for code in all_eligible_codes}
        return target_date, navs

    monkeypatch.setattr(rollup_module, "_fetch_with_fallback", _fake_fetch)

    result = run_period_return_rollup(db, today=today)

    assert result.as_of_date == today
    assert result.returns_computed == len(PERIODS) * result.eligible_variant_count

    rows = (
        db.query(FundPeriodReturn)
        .filter(FundPeriodReturn.scheme_variant_id == tracked.id)
        .order_by(FundPeriodReturn.period)
        .all()
    )
    assert {r.period for r in rows} == {p for p, _ in PERIODS}
    for row in rows:
        assert float(row.return_pct) == pytest.approx(25.0)
        assert row.as_of_date == today

    # Re-running with a DIFFERENT value must overwrite, not accumulate --
    # same convention as fund_metrics.
    def _fake_fetch_v2(target_date: date):
        navs = {tracked.amfi_code: (110.0 if target_date == today else 100.0)}
        return target_date, navs

    monkeypatch.setattr(rollup_module, "_fetch_with_fallback", _fake_fetch_v2)
    run_period_return_rollup(db, today=today)

    rows_after = (
        db.query(FundPeriodReturn).filter(FundPeriodReturn.scheme_variant_id == tracked.id).all()
    )
    assert len(rows_after) == len(PERIODS)  # still one row per period, not doubled
    for row in rows_after:
        assert float(row.return_pct) == pytest.approx(10.0)


def test_rollup_handles_missing_anchor_gracefully(seeded_variants, db, monkeypatch):
    today = date(2026, 10, 20)

    def _fake_fetch(target_date: date):
        if target_date == today:
            return today, {v.amfi_code: 100.0 for v in seeded_variants}
        return None  # every anchor date "fails" (e.g. fetch errors every time)

    monkeypatch.setattr(rollup_module, "_fetch_with_fallback", _fake_fetch)

    result = run_period_return_rollup(db, today=today)

    assert result.returns_computed == 0
    assert result.periods_unavailable is not None
    assert all(count == result.eligible_variant_count for count in result.periods_unavailable.values())


def test_fetch_with_fallback_skips_a_weekend_only_accrual_snapshot(monkeypatch):
    """Real bug found via a live run against the real AMFI portal: a
    Saturday returns a real, non-empty response (~600 rows, Overnight/
    Liquid-only — those categories price daily even on non-trading days)
    but is missing the whole equity/most-debt universe. Must be treated
    the same as empty and fall back further, not accepted as-is."""
    saturday = date(2026, 9, 19)
    friday = date(2026, 9, 18)

    # fetch_portal_history_for_date returns a marker string carrying the
    # date it was asked for; parse_portal_history_navs decodes that same
    # marker back into a per-date dict -- together they stand in for a
    # real round trip without a network call.
    monkeypatch.setattr(rollup_module, "fetch_portal_history_for_date", lambda target_date: str(target_date))
    monkeypatch.setattr(
        rollup_module,
        "parse_portal_history_navs",
        lambda raw_text: (
            {f"CODE{i}": 1.0 for i in range(1500)}  # friday: a real, full-sized universe
            if raw_text == str(friday)
            else {"145481": 1478.0}  # saturday: a real but accrual-only (undersized) snapshot
        ),
    )

    result = _fetch_with_fallback(saturday)

    assert result is not None
    actual_date, navs = result
    assert actual_date == friday  # stepped back past the undersized Saturday snapshot
    assert len(navs) == 1500
