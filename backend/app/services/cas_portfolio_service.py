"""Builds the Portfolio Analysis Overview (invested capital, current
value, realized/unrealized gain, portfolio XIRR) from a CAS's full
parsed transaction ledger — Phase 1 of the larger Portfolio Analysis
intelligence module (spec sections 4-5). Only covers schemes matched to
this platform's own fund catalog by ISIN (same matching cas_service.py
already does for the manual-form pre-fill) — a scheme not in our catalog
has no NAV history we can use to value it today, so it's reported as
excluded, never guessed at.

Cash-flow treatment (why this isn't "every transaction is a cash flow"):
switches/STP move money between two schemes already inside this same
portfolio, so they never leave or enter the investor's pocket — excluded
from both "invested capital" and XIRR cash flows, matching the CAS
Portfolio Analysis spec's explicit "Do not blindly treat every CAS
transaction as an external cash flow." A switch's *unit cost basis* is
still tracked correctly by the FIFO engine (analytics/cost_basis.py)
regardless — that's a separate concern from which transactions represent
real money moving in or out.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from analytics.cost_basis import apply_fifo
from analytics.xirr import xirr
from app.models.reference import Scheme, SchemeVariant
from app.repositories import fund_repository
from data_pipeline.normalization.cas_parser import CASTransaction

# Real external cash leaving the investor's pocket into a fund.
_OUTFLOW_TYPES = {"PURCHASE", "SIP"}
# Real external cash returning to the investor's pocket from a fund.
_INFLOW_TYPES = {"REDEMPTION", "SWP", "DIVIDEND"}  # DIVIDEND = a cash payout, not reinvested


def build_cas_overview(db: Session, transactions: list[CASTransaction]) -> dict:
    by_isin: dict[str, list[CASTransaction]] = {}
    for t in transactions:
        by_isin.setdefault(t.isin, []).append(t)

    variants_by_isin: dict[str, tuple[SchemeVariant, Scheme]] = {}
    if by_isin:
        rows = (
            db.query(SchemeVariant, Scheme)
            .join(Scheme, SchemeVariant.scheme_id == Scheme.id)
            .filter(SchemeVariant.isin.in_(by_isin.keys()))
            .all()
        )
        variants_by_isin = {variant.isin: (variant, scheme) for variant, scheme in rows}

    per_scheme: list[dict] = []
    unmatched: list[dict] = []
    portfolio_cash_flows: list[tuple[date, float]] = []
    total_invested = 0.0
    total_current_value = 0.0
    total_realized_gain = 0.0
    total_unrealized_gain = 0.0

    for isin, txns in by_isin.items():
        found = variants_by_isin.get(isin)
        if found is None:
            unmatched.append({"isin": isin, "scheme_name": txns[0].scheme_name or isin})
            continue

        variant, scheme = found
        cost_basis = apply_fifo([(t.transaction_date, t.units, t.amount) for t in txns])

        nav_series = fund_repository.get_nav_series(db, variant.id)
        latest_nav = float(nav_series.iloc[-1]) if not nav_series.empty else None
        latest_nav_date = nav_series.index[-1].date() if not nav_series.empty else None
        current_value = cost_basis.remaining_units * latest_nav if latest_nav is not None else None
        unrealized_gain = current_value - cost_basis.remaining_cost if current_value is not None else None

        scheme_invested = sum(t.amount for t in txns if t.transaction_type in _OUTFLOW_TYPES)
        total_invested += scheme_invested
        total_realized_gain += cost_basis.realized_gain
        if current_value is not None:
            total_current_value += current_value
            total_unrealized_gain += unrealized_gain

        for t in txns:
            if t.transaction_type in _OUTFLOW_TYPES:
                portfolio_cash_flows.append((t.transaction_date, -abs(t.amount)))
            elif t.transaction_type in _INFLOW_TYPES:
                portfolio_cash_flows.append((t.transaction_date, abs(t.amount)))
            # SWITCH_IN/SWITCH_OUT/STP_IN/STP_OUT/DIVIDEND_REINVESTMENT/BONUS/
            # OTHER/REVERSAL: not an external cash flow, intentionally excluded.
        if current_value is not None and current_value > 0 and latest_nav_date is not None:
            # This scheme's own share of the terminal (today's) portfolio
            # value, dated to when that value is actually as-of -- not
            # blended into one portfolio-wide date, since different
            # schemes' NAV data can be fresher or staler than each other.
            portfolio_cash_flows.append((latest_nav_date, current_value))

        per_scheme.append(
            {
                "fund_id": scheme.id,
                "scheme_name": scheme.name,
                "isin": isin,
                "invested_amount": round(scheme_invested, 2),
                "realized_gain": round(cost_basis.realized_gain, 2),
                "remaining_units": round(cost_basis.remaining_units, 4),
                "weighted_average_purchase_nav": (
                    round(cost_basis.weighted_average_purchase_nav, 4)
                    if cost_basis.weighted_average_purchase_nav is not None
                    else None
                ),
                "current_nav": round(latest_nav, 4) if latest_nav is not None else None,
                "current_nav_date": latest_nav_date,
                "current_value": round(current_value, 2) if current_value is not None else None,
                "unrealized_gain": round(unrealized_gain, 2) if unrealized_gain is not None else None,
            }
        )

    portfolio_xirr = xirr(portfolio_cash_flows)

    return {
        "total_invested": round(total_invested, 2),
        "total_current_value": round(total_current_value, 2),
        "total_realized_gain": round(total_realized_gain, 2),
        "total_unrealized_gain": round(total_unrealized_gain, 2),
        "total_gain": round(total_realized_gain + total_unrealized_gain, 2),
        "portfolio_xirr_pct": round(portfolio_xirr * 100, 2) if portfolio_xirr is not None else None,
        "matched_scheme_count": len(per_scheme),
        "per_scheme": per_scheme,
        "unmatched_schemes": unmatched,
    }
