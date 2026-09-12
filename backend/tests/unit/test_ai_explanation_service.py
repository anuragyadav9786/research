"""Unit tests for the Phase 12 AI Explanation Layer's guardrail and
orchestration logic. No live LLM calls — `_call_llm` is monkeypatched
throughout, per the same pattern used for the AMFI HTTP client in Phase 3.
"""
import pytest

from app.services import ai_explanation_service as svc


def test_extract_numbers_hand_cases():
    text = "The fund returned -10.48% over 1 year, with a Sharpe of -0.32 and beta 0.09."
    assert svc.extract_numbers(text) == [-10.48, 1.0, -0.32, 0.09]


def test_extract_numbers_empty_text():
    assert svc.extract_numbers("No numbers here.") == []


def test_flatten_numeric_facts_excludes_bools():
    facts = {"fund_name": "Sample Fund", "return_1y_pct": -10.48, "drawdown_recovered": False, "regimes_total": 4}
    result = svc.flatten_numeric_facts(facts)
    assert -10.48 in result
    assert 4 in result
    assert False not in result and True not in result
    assert len(result) == 2  # only the two real numeric facts


def test_validate_no_fabricated_numbers_accepts_exact_match():
    facts = {"return_1y_pct": -10.48, "sharpe_ratio": -0.32}
    text = "The fund returned -10.48% with a Sharpe ratio of -0.32."
    result = svc.validate_no_fabricated_numbers(text, facts)
    assert result["valid"] is True
    assert result["unmatched_numbers"] == []


def test_validate_no_fabricated_numbers_allows_reasonable_rounding():
    facts = {"return_1y_pct": -10.48}
    text = "The fund returned approximately -10% over the past year."
    result = svc.validate_no_fabricated_numbers(text, facts)
    assert result["valid"] is True


def test_validate_no_fabricated_numbers_rejects_fabricated_number():
    facts = {"return_1y_pct": -10.48, "sharpe_ratio": -0.32}
    text = "The fund returned -10.48% and has beaten its benchmark in 9 of the last 10 years."
    result = svc.validate_no_fabricated_numbers(text, facts)
    assert result["valid"] is False
    assert 9.0 in result["unmatched_numbers"]
    assert 10.0 in result["unmatched_numbers"]


def test_validate_no_fabricated_numbers_rejects_wildly_wrong_number():
    facts = {"volatility_pct": 15.10}
    text = "The fund has a volatility of 45%."
    result = svc.validate_no_fabricated_numbers(text, facts)
    assert result["valid"] is False


def test_build_prompt_includes_all_facts_and_safety_rules():
    facts = {"fund_name": "Sample Fund", "return_1y_pct": -10.48}
    prompt = svc.build_prompt(facts)
    assert "Sample Fund" in prompt
    assert "-10.48" in prompt
    assert "ONLY the numbers given below" in prompt
    assert "future performance" in prompt


def test_build_fund_facts_omits_unavailable_sections():
    returns = {"windows": {"1y": {"available": True, "cagr_pct": -10.48}, "3y": {"available": False}}}
    risk = {"available": False}
    drawdown = {"available": False}
    rolling = {"available": False}
    facts = svc.build_fund_facts(
        "Sample Fund", "Equity - Large Cap", "Sample AMC", "Nifty 50",
        returns, risk, drawdown, rolling, regime_behavior=None, portfolio_dna=None,
    )
    assert facts["return_1y_pct"] == -10.48
    assert "return_3y_pct" not in facts
    assert "volatility_pct" not in facts
    assert "max_drawdown_pct" not in facts
    assert "rolling_window_years" not in facts


def test_generate_fund_summary_unavailable_when_not_configured(monkeypatch):
    monkeypatch.setattr(svc, "_call_llm", lambda prompt: (_ for _ in ()).throw(
        svc.AIServiceUnavailable("no key configured")
    ))
    result = svc.generate_fund_summary({"fund_name": "Sample Fund"})
    assert result["available"] is False
    assert "no key configured" in result["reason"]
    assert result["summary"] is None


def test_generate_fund_summary_returns_verified_summary(monkeypatch):
    facts = {"fund_name": "Sample Fund", "return_1y_pct": -10.48}
    monkeypatch.setattr(svc, "_call_llm", lambda prompt: "Sample Fund returned -10.48% over the past year.")
    result = svc.generate_fund_summary(facts)
    assert result["available"] is True
    assert result["summary"] == "Sample Fund returned -10.48% over the past year."


def test_generate_fund_summary_discards_output_with_fabricated_numbers(monkeypatch):
    facts = {"fund_name": "Sample Fund", "return_1y_pct": -10.48}
    monkeypatch.setattr(
        svc, "_call_llm",
        lambda prompt: "Sample Fund has outperformed 95% of its peers.",
    )
    result = svc.generate_fund_summary(facts)
    assert result["available"] is False
    assert result["summary"] is None
    assert "95" in result["reason"] or "95.0" in result["reason"]
