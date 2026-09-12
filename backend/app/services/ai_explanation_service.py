"""AI Explanation Layer — Phase 12 (Section 24).

Architecture, per the product spec:

    Python analytics (already computed, deterministic)
            |
            v
    Structured JSON "facts" (this module: build_fund_facts)
            |
            v
    AI explanation (this module: generate_fund_summary — a single LLM call)
            |
            v
    Verified human-readable summary (this module: validate_no_fabricated_numbers)

The AI never computes a financial number — it only ever sees the facts
dict built by `build_fund_facts` from already-computed analytics output,
and everything it writes is checked against that same dict before being
returned. This is the load-bearing guarantee of the whole layer, so it is
enforced in code (`validate_no_fabricated_numbers`), not just requested in
the prompt.
"""
from __future__ import annotations

import re

from app.core.config import get_settings

NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


class AIServiceUnavailable(RuntimeError):
    """Raised when no LLM credentials are configured. Callers should
    surface this as a clear "not configured" response, never a silent
    fallback or a fabricated summary."""


def build_fund_facts(
    fund_name: str,
    category: str,
    amc_name: str,
    benchmark_name: str | None,
    returns: dict,
    risk: dict,
    drawdown: dict,
    rolling: dict,
    regime_behavior: dict | None,
    portfolio_dna: dict | None,
) -> dict:
    """Curate a small, flat, named dict of facts from already-computed
    analytics output — the ONLY data the AI is given. Fields are omitted
    (never set to a fabricated placeholder) when the underlying analytics
    reported them unavailable, per the same "no fabrication" rule that
    governs every deterministic function upstream of this one.
    """
    facts: dict = {"fund_name": fund_name, "category": category, "amc_name": amc_name}
    if benchmark_name:
        facts["benchmark_name"] = benchmark_name

    windows = returns.get("windows", {})
    for label in ("1y", "3y", "5y"):
        window = windows.get(label)
        if window and window.get("available"):
            facts[f"return_{label}_pct"] = window["cagr_pct"]

    if risk.get("available"):
        for key in ("volatility_pct", "sharpe_ratio", "sortino_ratio", "beta", "jensen_alpha_pct"):
            if risk.get(key) is not None:
                facts[key] = risk[key]

    if drawdown.get("available"):
        facts["max_drawdown_pct"] = drawdown["max_drawdown_pct"]
        facts["drawdown_recovered"] = drawdown["recovered"]

    if rolling.get("available"):
        facts["rolling_window_years"] = rolling["window_years"]
        if rolling["distribution"].get("median") is not None:
            facts["rolling_median_return_pct"] = rolling["distribution"]["median"]
        consistency = rolling.get("benchmark_consistency")
        if consistency and consistency.get("beat_rate_pct") is not None:
            facts["rolling_beat_benchmark_pct"] = consistency["beat_rate_pct"]

    if regime_behavior:
        facts["regimes_outperformed"] = regime_behavior["regimes_outperformed"]
        facts["regimes_total"] = regime_behavior["regimes_with_comparison"]

    if portfolio_dna and portfolio_dna.get("available"):
        facts["top5_holdings_weight_pct"] = portfolio_dna["top5_weight_pct"]
        facts["concentration_hhi"] = portfolio_dna["hhi"]
        facts["concentration_label"] = portfolio_dna["hhi_label"]

    return facts


def extract_numbers(text: str) -> list[float]:
    """All numeric literals appearing in a piece of text (percent signs,
    currency symbols and other surrounding characters are ignored — only
    the numeric value itself is extracted)."""
    return [float(match) for match in NUMBER_PATTERN.findall(text)]


def flatten_numeric_facts(facts: dict) -> list[float]:
    """Numeric leaf values from a facts dict — explicitly excludes bools
    (a `True`/`False` fact must never license the AI to write a bare "1"
    or "0" and have it wave through as "matching" data)."""
    return [v for v in facts.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _within_tolerance(extracted: float, fact: float) -> bool:
    tolerance = max(0.1, abs(fact) * 0.1)
    return abs(extracted - fact) <= tolerance


def validate_no_fabricated_numbers(text: str, facts: dict) -> dict:
    """The core safety check: every number the AI wrote must be traceable,
    within a reasonable rounding tolerance (10% relative, 0.1 absolute
    floor — accommodates the AI naturally rounding "-10.48%" to "-10%"),
    to some numeric fact it was actually given.

    Returns {"valid": bool, "unmatched_numbers": [...]} — the caller (see
    `generate_fund_summary`) must not surface AI text that fails this
    check; a summary that fails is a bug in the model's output, not
    something to relax the check for.
    """
    allowed = flatten_numeric_facts(facts)
    unmatched = [
        n for n in extract_numbers(text)
        if not any(_within_tolerance(n, fact) for fact in allowed)
    ]
    return {"valid": len(unmatched) == 0, "unmatched_numbers": unmatched}


def build_prompt(facts: dict) -> str:
    facts_lines = "\n".join(f"- {key}: {value}" for key, value in facts.items())
    return f"""You are a mutual fund research assistant. You will be given a fixed set of
already-computed data points about one fund. Write a concise (3-5 sentence) professional
research summary of the fund's historical behaviour for an investor.

STRICT RULES — violating any of these makes your answer unusable:
1. Use ONLY the numbers given below. Do not calculate, estimate, round to a different
   precision than shown, or introduce any number that is not in this list.
2. Do not state or imply anything about future performance. Only describe what the
   historical data shows.
3. Do not invent holdings, managers, dates, or comparisons not present in the data below.
4. If the data is limited, say so plainly rather than filling gaps with generic language.

DATA:
{facts_lines}

Write the summary now, as plain text with no headings or bullet points."""


def _call_llm(prompt: str) -> str:
    """The only function in this module that makes a network call — kept
    small and separate specifically so tests can monkeypatch it instead of
    hitting the real API (see backend/tests for the mocking pattern used
    throughout this codebase, e.g. the AMFI HTTP client in Phase 3)."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise AIServiceUnavailable(
            "AI explanation layer is not configured: no ANTHROPIC_API_KEY is set. "
            "This is expected in a zero-budget/dev environment — see docs/api.md."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.ai_explanation_model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def generate_fund_summary(facts: dict) -> dict:
    """Generate and verify an AI research summary for one fund.

    Returns:
        {"available": True, "summary": str, "facts_used": facts}
        {"available": False, "reason": str, "facts_used": facts}

    `available: False` covers two distinct cases, both surfaced honestly
    rather than papered over: the AI service isn't configured
    (AIServiceUnavailable), or the model's output failed the
    no-fabricated-numbers check (a bug in that specific generation, not a
    reason to relax the check or serve unverified text anyway).
    """
    prompt = build_prompt(facts)
    try:
        summary = _call_llm(prompt)
    except AIServiceUnavailable as exc:
        return {"available": False, "reason": str(exc), "facts_used": facts, "summary": None}

    validation = validate_no_fabricated_numbers(summary, facts)
    if not validation["valid"]:
        return {
            "available": False,
            "reason": (
                "Generated summary contained numbers not present in the provided data "
                f"({validation['unmatched_numbers']}) and was discarded rather than shown."
            ),
            "facts_used": facts,
            "summary": None,
        }

    return {"available": True, "reason": None, "facts_used": facts, "summary": summary}
