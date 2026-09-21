import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ThinkFin Research Engine"
    environment: str = "development"
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/thinkfin"
    # NoDecode: pydantic-settings' default env-var handling for list fields
    # requires strict JSON (e.g. '["a","b"]') and raises a startup-crashing
    # SettingsError on anything else — a one-character mistake in a host's
    # dashboard (missing bracket/quote) takes the whole app down. The
    # validator below also accepts a plain comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    analytics_version: str = "v0.1.0"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value.startswith("["):
            return json.loads(value)
        return [origin.strip() for origin in value.split(",") if origin.strip()]

    # Annualized, decimal form (e.g. 0.07 = 7%). Used by the Sharpe ratio.
    # Documented assumption — see analytics/risk.py for methodology notes.
    risk_free_rate: float = 0.07

    # AI Explanation Layer (Phase 12) — reads only precomputed structured
    # facts, never computes a number itself (Rule 4). None by default: the
    # feature is architecturally complete but not enabled without a real
    # key. See docs/api.md for what "not configured" looks like at the API.
    anthropic_api_key: str | None = None
    ai_explanation_model: str = "claude-sonnet-5"

    # Benchmark Data Engine — NSE (niftyindices.com) provider. Enabled by
    # request; its request/response shape (data_pipeline/sources/
    # benchmarks/nse.py) was NOT verified against a live response before
    # this was turned on — the sandbox that shipped it had no outbound
    # network access at all (confirmed via an explicit 403
    # organization-policy denial on niftyindices.com, not a transient
    # failure). This is a deliberate, informed choice, not an oversight:
    # nse.py's validation (data_pipeline/validation/benchmark_validation.py)
    # rejects anything malformed, and a shape mismatch fails a fetch
    # attempt closed — the UI still only ever shows "Data unavailable" or
    # a real number, never a fabricated one. Still needs confirming
    # against the live endpoint from an environment with real network
    # access. See docs/data-sources.md section 4.
    benchmark_nse_provider_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
