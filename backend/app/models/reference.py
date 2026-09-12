"""Core reference / fund-identity tables: AMC -> Fund Family -> Scheme -> Variant."""
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint, func
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
