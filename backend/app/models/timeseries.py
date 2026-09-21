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
