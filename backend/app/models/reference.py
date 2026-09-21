"""Core reference / fund-identity tables: AMC -> Fund Family -> Scheme -> Variant."""
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AMC(Base):
    __tablename__ = "amcs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fund_families: Mapped[list["FundFamily"]] = relationship(back_populates="amc")


class FundFamily(Base):
    __tablename__ = "fund_families"

    id: Mapped[int] = mapped_column(primary_key=True)
    amc_id: Mapped[int] = mapped_column(ForeignKey("amcs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    amc: Mapped["AMC"] = relationship(back_populates="fund_families")
    schemes: Mapped[list["Scheme"]] = relationship(back_populates="fund_family")

    __table_args__ = (UniqueConstraint("amc_id", "name", name="uq_fund_family_amc_name"),)


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    index_code: Mapped[str | None] = mapped_column(String(50))
    # Which BenchmarkProvider (data_pipeline/sources/benchmarks/) knows how
    # to fetch this benchmark's price history — "NSE", "BSE", "CRISIL",
    # "MSCI", ... NULL means no provider is wired up for it yet (e.g. the
    # seed script's synthetic sample benchmarks), so lazy_benchmark_backfill
    # correctly treats it as unfetchable rather than guessing a provider.
    provider: Mapped[str | None] = mapped_column(String(50))
    # The provider's own identifier for the index (e.g. "NIFTY 100 TRI") —
    # kept distinct from `name` (this platform's own display name, already
    # used across the UI/API) since a provider's symbol/query key doesn't
    # always match how we want the index shown to an investor.
    symbol: Mapped[str | None] = mapped_column(String(100))
    # "TRI" (Total Returns Index, includes reinvested dividends) or
    # "PRICE" (price-return only, no dividend reinvestment) — mutual fund
    # scheme benchmarks are conventionally TRI; kept explicit rather than
    # assumed so a PRICE index is never silently compared against a fund's
    # total return (Rule: never conflate a price index with a TRI benchmark).
    benchmark_type: Mapped[str | None] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    # Denormalized cache of max(benchmark_history.date) for this benchmark —
    # lets the freshness check (lazy_benchmark_backfill.py) skip a query
    # against benchmark_history on the common "already fresh" path. Kept in
    # sync by write_benchmark_points; never the source of truth, which is
    # always benchmark_history itself.
    last_data_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("benchmark_type in ('TRI', 'PRICE')", name="ck_benchmark_type"),
    )


class Scheme(Base):
    __tablename__ = "schemes"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_family_id: Mapped[int] = mapped_column(ForeignKey("fund_families.id"), nullable=False)
    benchmark_id: Mapped[int | None] = mapped_column(ForeignKey("benchmarks.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. Large Cap, Mid Cap, Debt...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fund_family: Mapped["FundFamily"] = relationship(back_populates="schemes")
    variants: Mapped[list["SchemeVariant"]] = relationship(back_populates="scheme")
    benchmark: Mapped["Benchmark | None"] = relationship()


class FundBenchmarkHistory(Base):
    """Historical, scheme-level benchmark assignment — named and shaped
    after FundManagerHistory below (same start_date/end_date-per-scheme
    pattern), since a scheme's benchmark can change over time just like
    its manager can, and `Scheme.benchmark_id` alone only ever holds the
    current one.

    `Scheme.benchmark_id` is kept as the authoritative CURRENT pointer
    (every existing reader of it keeps working unchanged); this table is
    additive, for periods before the current one. See
    fund_repository.get_effective_benchmark_id for how the two combine.

    end_date NULL means "still in effect". start_date NULL means "the date
    this benchmark started applying isn't known" — never filled with a
    guessed date; a row is only ever inserted with a real, sourced date or
    left NULL, per the platform's no-fabricated-data rule.
    """

    __tablename__ = "fund_benchmark_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("schemes.id"), nullable=False)
    benchmark_id: Mapped[int] = mapped_column(ForeignKey("benchmarks.id"), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    # Where this assignment came from, e.g. "scheme.benchmark_id (legacy
    # pointer, migrated)", "amc_factsheet", "manual_curation" — never left
    # implicit, so a mapping's provenance is always traceable.
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_fund_benchmark_history_scheme_id", "scheme_id"),
        # Only one open-ended ("current") assignment per scheme at a time —
        # a new one must close the previous with end_date before opening,
        # never two "current" benchmarks for the same scheme simultaneously.
        Index(
            "uq_fund_benchmark_history_current_per_scheme",
            "scheme_id",
            unique=True,
            postgresql_where=text("end_date IS NULL"),
        ),
    )


class SchemeVariant(Base):
    """The unit NAV history actually attaches to: plan x option combination."""

    __tablename__ = "scheme_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("schemes.id"), nullable=False)
    plan: Mapped[str] = mapped_column(String(20), nullable=False)  # direct | regular
    option: Mapped[str] = mapped_column(String(20), nullable=False)  # growth | idcw
    amfi_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    isin: Mapped[str | None] = mapped_column(String(20), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set once a full NAV history backfill (data_pipeline/orchestration/
    # lazy_nav_backfill.py, via api.mfapi.in) has run for this variant, so
    # repeat fund-page views don't re-fetch on every request. NULL means
    # "not yet backfilled" — either brand new, or the daily feed's ongoing
    # NAV points are all we have so far.
    nav_history_backfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scheme: Mapped["Scheme"] = relationship(back_populates="variants")

    __table_args__ = (
        CheckConstraint("plan in ('direct', 'regular')", name="ck_variant_plan"),
        CheckConstraint("option in ('growth', 'idcw')", name="ck_variant_option"),
    )


class Security(Base):
    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))
    # Null for non-equity instruments (bonds, etc.) where market-cap
    # classification doesn't apply, or where we simply don't have the
    # classification yet — never guessed to fill the field.
    market_cap_category: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        CheckConstraint(
            "market_cap_category in ('large_cap', 'mid_cap', 'small_cap', 'other')",
            name="ck_security_market_cap_category",
        ),
    )


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    parent_sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))


class FundManager(Base):
    __tablename__ = "fund_managers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class FundManagerHistory(Base):
    __tablename__ = "fund_manager_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("schemes.id"), nullable=False)
    manager_id: Mapped[int] = mapped_column(ForeignKey("fund_managers.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)


class MarketRegime(Base):
    __tablename__ = "market_regimes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    regime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
