"""Investor-facing portfolio tables — kept logically separate from fund reference data
so this group could be split into its own service/schema later without touching
the fund research core."""
from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_tolerance: Mapped[str | None] = mapped_column(String(50))
    horizon_years: Mapped[int | None] = mapped_column()
    goal: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvestorPortfolio(Base):
    __tablename__ = "investor_portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    investor_profile_id: Mapped[int] = mapped_column(ForeignKey("investor_profiles.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvestorPortfolioHolding(Base):
    __tablename__ = "investor_portfolio_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("investor_portfolios.id"), nullable=False)
    scheme_variant_id: Mapped[int] = mapped_column(ForeignKey("scheme_variants.id"), nullable=False)
    units: Mapped[float | None] = mapped_column(Numeric(18, 4))
    invested_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))


class PortfolioAnalysis(Base):
    __tablename__ = "portfolio_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("investor_portfolios.id"), nullable=False)
    analysis_json: Mapped[str] = mapped_column(nullable=False)  # JSON-serialized structured output
    calc_date: Mapped[date] = mapped_column(nullable=False)
    analytics_version: Mapped[str] = mapped_column(String(20), nullable=False)
