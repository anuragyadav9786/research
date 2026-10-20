"""NAV/benchmark history, holdings snapshots, and computed metrics."""
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    url: Mapped[str | None] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # amfi | amc | sebi | nse | rbi | mfapi | manual


class DataIngestionRun(Base):
    __tablename__ = "data_ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_downloaded: Mapped[int] = mapped_column(default=0)
    records_accepted: Mapped[int] = mapped_column(default=0)
    records_rejected: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|failed
    error_message: Mapped[str | None] = mapped_column(String(2000))


class NavHistory(Base):
    __tablename__ = "nav_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_variant_id: Mapped[int] = mapped_column(ForeignKey("scheme_variants.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    nav: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("scheme_variant_id", "date", name="uq_nav_variant_date"),
        CheckConstraint("nav > 0", name="ck_nav_positive"),
    )


class BenchmarkHistory(Base):
    """One benchmark's daily price series — shared across every scheme that
    uses it (see Scheme.benchmark_id / FundBenchmarkHistory), never stored
    per-fund. This is the "benchmark_prices" table in the benchmark-engine
    design: intentionally just (benchmark_id, date, value) — no OHLC —
    since that's all the research engine's return/risk calculations need.
    """

    __tablename__ = "benchmark_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    benchmark_id: Mapped[int] = mapped_column(ForeignKey("benchmarks.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # UNIQUE(benchmark_id, date) also serves as the benchmark_id+date
        # index the research engine's range reads need — no separate index
        # required (Postgres backs a unique constraint with one already).
        UniqueConstraint("benchmark_id", "date", name="uq_benchmark_date"),
        CheckConstraint("value > 0", name="ck_benchmark_value_positive"),
    )


class FundPeriodReturn(Base):
    """One scheme_variant's point-to-point return for one fixed lookback
    period (1m/3m/6m/1y/3y/5y), as of the most recent daily rollup run —
    the data behind the fund screener/"top performers" feature.

    Deliberately overwrite-style, same convention as FundMetric: each
    daily run REPLACES the existing row for a given (scheme_variant_id,
    period) rather than accumulating one row per day forever. No raw NAV
    time series is stored to produce this — each run fetches only the
    exact NAV points it needs (today's, plus one anchor point per period)
    from data_pipeline/sources/amfi/portal_history.py and discards them
    once the return is computed, so this table's size is bounded at
    (number of tracked schemes x 6 periods) regardless of how long the
    platform has been running. See data_pipeline/orchestration/
    period_return_rollup.py for the computation.

    `anchor_date` is the REAL date the anchor NAV was actually taken from
    (after stepping back over weekends/holidays with no published NAV) —
    kept so the API/UI can be honest that e.g. a "1 year" return is as of
    that exact anchor date, not silently assumed to be exactly 365 days
    back.
    """

    __tablename__ = "fund_period_returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_variant_id: Mapped[int] = mapped_column(ForeignKey("scheme_variants.id"), nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # "1m" | "3m" | "6m" | "1y" | "3y" | "5y"
    return_pct: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    anchor_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("scheme_variant_id", "period", name="uq_fund_period_return_identity"),
        CheckConstraint(
            "period in ('1m', '3m', '6m', '1y', '3y', '5y')", name="ck_fund_period_return_period"
        ),
    )


class PortfolioSnapshot(Base):
    """One monthly (or as-available) holdings disclosure for a scheme."""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("schemes.id"), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)

    __table_args__ = (UniqueConstraint("scheme_id", "as_of_date", name="uq_snapshot_scheme_date"),)


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("portfolio_snapshots.id"), nullable=False)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), nullable=False)
    weight_pct: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    market_value: Mapped[float | None] = mapped_column(Numeric(18, 2))

    __table_args__ = (
        CheckConstraint("weight_pct >= 0 AND weight_pct <= 100", name="ck_weight_pct_range"),
    )


class FundMetric(Base):
    """Precomputed analytics output — the API serves from here, never recalculates live."""

    __tablename__ = "fund_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_variant_id: Mapped[int] = mapped_column(ForeignKey("scheme_variants.id"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    calc_date: Mapped[date] = mapped_column(Date, nullable=False)
    analytics_version: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "scheme_variant_id", "metric_name", "calc_date", "analytics_version",
            name="uq_metric_identity",
        ),
    )


class AnalyticsRun(Base):
    __tablename__ = "analytics_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    analytics_version: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
