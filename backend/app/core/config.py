from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ThinkFin Research Engine"
    environment: str = "development"
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/thinkfin"
    cors_origins: list[str] = ["http://localhost:3000"]
    analytics_version: str = "v0.1.0"

    # Annualized, decimal form (e.g. 0.07 = 7%). Used by the Sharpe ratio.
    # Documented assumption — see analytics/risk.py for methodology notes.
    risk_free_rate: float = 0.07


@lru_cache
def get_settings() -> Settings:
    return Settings()
