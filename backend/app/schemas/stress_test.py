"""Response schema for Phase 11's Stress-Test Engine."""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.funds import DISCLAIMER

HYPOTHETICAL_NOTICE = (
    "These are hypothetical scenarios for illustration, not predictions of actual future "
    "performance. Modeled scenarios use simplified historical relationships (beta, disclosed "
    "sector/market-cap exposure) and do not capture real-world contagion, liquidity effects, "
    "or correlation shifts during actual market stress."
)


class ScenarioResult(BaseModel):
    scenario_id: str
    name: str
    description: str
    shock_type: str
    shock_pct: float | None
    available: bool
    reason: str | None
    exposure_pct: float | None
    estimated_impact_pct: float | None


class StressTestResponse(BaseModel):
    fund_beta: float | None
    scenarios: list[ScenarioResult]
    hypothetical_notice: str = HYPOTHETICAL_NOTICE
    disclaimer: str = DISCLAIMER
