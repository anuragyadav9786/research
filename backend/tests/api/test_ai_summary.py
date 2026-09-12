"""API tests for the Phase 12 AI Explanation Layer endpoint, against the
real Phase 2 seed data. No live LLM calls — this test suite runs without
ANTHROPIC_API_KEY configured (the expected state in CI/dev), verifying
the "not configured" path, and separately monkeypatches the service's
_call_llm to verify the "available" path without hitting the real API.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import Scheme
from app.services import ai_explanation_service

client = TestClient(app)


@pytest.fixture(scope="module")
def bluechip_id() -> int:
    db = SessionLocal()
    try:
        scheme = db.query(Scheme).filter(Scheme.name == "Northbridge Bluechip Equity Fund").first()
        assert scheme is not None, "requires Phase 2 seed data to be loaded"
        return scheme.id
    finally:
        db.close()


def test_ai_summary_reports_not_configured_without_api_key(bluechip_id, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.core.config import get_settings
    get_settings.cache_clear()

    response = client.get(f"/api/funds/{bluechip_id}/ai-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "ANTHROPIC_API_KEY" in body["reason"]
    assert body["summary"] is None
    # facts_used is still populated from real computed analytics, even though no summary was generated
    assert body["facts_used"]["fund_name"] == "Northbridge Bluechip Equity Fund"
    assert "return_1y_pct" in body["facts_used"]
    get_settings.cache_clear()


def test_ai_summary_facts_reconcile_with_returns_endpoint(bluechip_id):
    ai_response = client.get(f"/api/funds/{bluechip_id}/ai-summary").json()
    returns_response = client.get(f"/api/funds/{bluechip_id}/returns").json()
    assert ai_response["facts_used"]["return_1y_pct"] == returns_response["windows"]["1y"]["cagr_pct"]


def test_ai_summary_returns_verified_text_when_llm_mocked(bluechip_id, monkeypatch):
    def fake_call_llm(prompt):
        return "This fund has a track record shaped by the figures provided."

    monkeypatch.setattr(ai_explanation_service, "_call_llm", fake_call_llm)
    response = client.get(f"/api/funds/{bluechip_id}/ai-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["summary"] == "This fund has a track record shaped by the figures provided."


def test_ai_summary_discards_fabricated_output_when_llm_mocked(bluechip_id, monkeypatch):
    monkeypatch.setattr(
        ai_explanation_service, "_call_llm",
        lambda prompt: "This fund has outperformed 99% of category peers.",
    )
    response = client.get(f"/api/funds/{bluechip_id}/ai-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["summary"] is None
    assert "99" in body["reason"]


def test_ai_summary_unknown_fund_returns_404():
    response = client.get("/api/funds/999999/ai-summary")
    assert response.status_code == 404
