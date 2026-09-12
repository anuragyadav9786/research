"""Shared fixtures for the backend test suite.

Autouse-disables the Phase 15 lazy NAV backfill (mfapi.in) for every test
by default. Most tests exercise fund endpoints against Phase 2's fictional
sample scheme codes ("SMP..."), which aren't real AMFI codes — without
this, every API test that resolves a variant would attempt (and fail) a
real outbound HTTP call to api.mfapi.in on every run, since
nav_history_backfilled_at starts unset for all seed data. Tests that
specifically exercise the lazy backfill itself
(tests/integration/test_lazy_nav_backfill.py, tests/unit/test_mfapi_*)
monkeypatch the mfapi client/orchestration function directly instead and
don't rely on this fixture.
"""
from __future__ import annotations

import pytest

import app.api.funds as funds_module
from data_pipeline.orchestration.lazy_nav_backfill import LazyBackfillOutcome


@pytest.fixture(autouse=True)
def _disable_lazy_nav_backfill(monkeypatch):
    monkeypatch.setattr(
        funds_module, "ensure_nav_history", lambda db, variant: LazyBackfillOutcome(attempted=False)
    )
