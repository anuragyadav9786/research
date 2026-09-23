"""Builds the Portfolio Analysis Overview (invested capital, current
value, realized/unrealized gain, portfolio XIRR, per-scheme contribution,
and holding-period analysis) from a CAS's full parsed transaction ledger
— Phases 1-3 of the larger Portfolio Analysis intelligence module (spec
sections 4-5, 12, 15). Only covers schemes matched to this platform's own
fund catalog by ISIN (same matching cas_service.py already does for the
manual-form pre-fill) — a scheme not in our catalog has no NAV history we
can use to value it today, so it's reported as excluded, never guessed at.

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

import statistics
from datetime import date

from sqlalchemy.orm import Session

from analytics.concentration import group_weights, herfindahl_hirschman_index, hhi_label, top_n_weight_pct
from analytics.cost_basis import apply_fifo
from analytics.xirr import xirr
from app.models.reference import Scheme, SchemeVariant
from app.repositories import fund_repository
from data_pipeline.normalization.cas_parser import CASTransaction
from data_pipeline.normalization.category_classification import classify_asset_class, classify_equity_style

# Real external cash leaving the investor's pocket into a fund.
_OUTFLOW_TYPES = {"PURCHASE", "SIP"}
# Real external cash returning to the investor's pocket from a fund.
_INFLOW_TYPES = {"REDEMPTION", "SWP", "DIVIDEND"}  # DIVIDEND = a cash payout, not reinvested

_CONCENTRATION_TOP_NS = (1, 3, 5, 10)

# Upper bound (in days) of each bucket, in order; None = unbounded (last bucket).
_HOLDING_PERIOD_BUCKETS: list[tuple[str, int | None]] = [
    ("< 1 year", 365),
    ("1-3 years", 365 * 3),
    ("3-5 years", 365 * 5),
    ("5+ years", None),
]


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
    # (scheme_name, amc_name, category, current_value) for every matched
    # scheme with a valid current value — the weight basis for concentration
    # and allocation, computed after the main loop.
    valued_schemes: list[tuple[str, str, str, float]] = []
    # (days_held, current_value) for every still-open lot we could price —
    # the basis for the portfolio-wide open-position holding-period summary.
    open_lot_days_values: list[tuple[int, float]] = []
    # holding_period_days for every FIFO-realized (sold/switched-out) lot
    # consumption, across every matched scheme.
    realized_holding_days: list[int] = []
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
        realized_holding_days.extend(c.holding_period_days for c in cost_basis.consumptions)

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
            if current_value > 0:
                valued_schemes.append((scheme.name, scheme.fund_family.amc.name, scheme.category, current_value))
            if latest_nav_date is not None:
                open_lot_days_values.extend(
                    ((latest_nav_date - lot.purchase_date).days, lot.units * latest_nav) for lot in cost_basis.open_lots
                )

        scheme_cash_flows: list[tuple[date, float]] = []
        for t in txns:
            if t.transaction_type in _OUTFLOW_TYPES:
                scheme_cash_flows.append((t.transaction_date, -abs(t.amount)))
            elif t.transaction_type in _INFLOW_TYPES:
                scheme_cash_flows.append((t.transaction_date, abs(t.amount)))
            # SWITCH_IN/SWITCH_OUT/STP_IN/STP_OUT/DIVIDEND_REINVESTMENT/BONUS/
            # OTHER/REVERSAL: not an external cash flow, intentionally excluded.
        if current_value is not None and current_value > 0 and latest_nav_date is not None:
            # This scheme's own share of the terminal (today's) portfolio
            # value, dated to when that value is actually as-of -- not
            # blended into one portfolio-wide date, since different
            # schemes' NAV data can be fresher or staler than each other.
            scheme_cash_flows.append((latest_nav_date, current_value))
        portfolio_cash_flows.extend(scheme_cash_flows)
        scheme_xirr = xirr(scheme_cash_flows)

        # A scheme still holding units we couldn't value (no NAV history)
        # has an incomplete gain figure — realized_gain alone understates
        # it, so its contribution to total gain is reported as unknown
        # rather than a misleadingly partial number.
        if cost_basis.remaining_units > 0 and unrealized_gain is None:
            scheme_gain = None
        else:
            scheme_gain = cost_basis.realized_gain + (unrealized_gain or 0.0)

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
                "scheme_xirr_pct": round(scheme_xirr * 100, 2) if scheme_xirr is not None else None,
                "weight_pct": None,  # filled below, once total_current_value is known
                "gain": round(scheme_gain, 2) if scheme_gain is not None else None,
                "contribution_to_gain_pct": None,  # filled below, once total_gain is known
            }
        )

    total_gain = total_realized_gain + total_unrealized_gain
    for entry in per_scheme:
        if entry["current_value"] is not None and total_current_value > 0:
            entry["weight_pct"] = round((entry["current_value"] / total_current_value) * 100, 2)
        if entry["gain"] is not None and total_gain != 0:
            entry["contribution_to_gain_pct"] = round((entry["gain"] / total_gain) * 100, 2)

    portfolio_xirr = xirr(portfolio_cash_flows)

    return {
        "total_invested": round(total_invested, 2),
        "total_current_value": round(total_current_value, 2),
        "total_realized_gain": round(total_realized_gain, 2),
        "total_unrealized_gain": round(total_unrealized_gain, 2),
        "total_gain": round(total_gain, 2),
        "portfolio_xirr_pct": round(portfolio_xirr * 100, 2) if portfolio_xirr is not None else None,
        "matched_scheme_count": len(per_scheme),
        "per_scheme": per_scheme,
        "unmatched_schemes": unmatched,
        "structure": _build_structure(valued_schemes),
        "holding_period": _holding_period_summary(open_lot_days_values, realized_holding_days),
    }


def _concentration_summary(weights_pct: list[float]) -> dict:
    hhi = herfindahl_hirschman_index(weights_pct)
    top_n = {f"top{n}_pct": round(top_n_weight_pct(weights_pct, n), 2) for n in _CONCENTRATION_TOP_NS}
    return {**top_n, "hhi": round(hhi, 1), "hhi_label": hhi_label(hhi)}


def _grouped_concentration(items: list[tuple[str, float]], total_value: float) -> dict:
    """Concentration summary one level up from individual schemes — e.g.
    "how concentrated is this portfolio by AMC" rather than by scheme.
    `items`: (label, value) pairs to group by label first."""
    grouped_values = group_weights(items)
    weights_pct = [(v / total_value) * 100 for v in grouped_values.values()] if total_value > 0 else []
    return {**_concentration_summary(weights_pct), "count": len(grouped_values)}


def _allocation_breakdown(items: list[tuple[str, float]], total_value: float) -> list[dict]:
    """`items`: (label, value) pairs. Sorted largest-first — the order a
    reader scans an allocation table in."""
    grouped_values = group_weights(items)
    breakdown = [
        {
            "label": label,
            "value": round(value, 2),
            "weight_pct": round((value / total_value) * 100, 2) if total_value > 0 else 0.0,
        }
        for label, value in grouped_values.items()
    ]
    return sorted(breakdown, key=lambda b: b["value"], reverse=True)


def _holding_period_bucket(days: int) -> str:
    for label, max_days in _HOLDING_PERIOD_BUCKETS:
        if max_days is None or days < max_days:
            return label
    return _HOLDING_PERIOD_BUCKETS[-1][0]


def _holding_period_summary(open_lot_days_values: list[tuple[int, float]], realized_days: list[int]) -> dict:
    """Portfolio Analysis §12: how long money has actually been held.
    `open_lot_days_values`: (days held so far, current value) for every
    still-open FIFO lot we could price — only lots whose scheme has NAV
    data are included, so this can under-count if some holdings are
    unpriced. `realized_days`: holding_period_days for every FIFO-realized
    (sold/switched-out) lot consumption, across every matched scheme.
    Every field is null/empty rather than a fabricated 0 when there's
    nothing of that kind to summarize (e.g. nothing has ever been sold)."""
    open_total_value = sum(v for _, v in open_lot_days_values)
    weighted_avg_open_days = (
        sum(days * v for days, v in open_lot_days_values) / open_total_value if open_total_value > 0 else None
    )

    bucket_values: dict[str, float] = {}
    for days, value in open_lot_days_values:
        label = _holding_period_bucket(days)
        bucket_values[label] = bucket_values.get(label, 0.0) + value
    open_value_by_bucket = [
        {
            "label": label,
            "value": round(bucket_values[label], 2),
            "weight_pct": round((bucket_values[label] / open_total_value) * 100, 2) if open_total_value > 0 else 0.0,
        }
        for label, _ in _HOLDING_PERIOD_BUCKETS
        if label in bucket_values
    ]

    return {
        "open_weighted_avg_days": round(weighted_avg_open_days) if weighted_avg_open_days is not None else None,
        "open_value_by_bucket": open_value_by_bucket,
        "realized_avg_days": round(statistics.mean(realized_days)) if realized_days else None,
        "realized_median_days": round(statistics.median(realized_days)) if realized_days else None,
        "realized_consumption_count": len(realized_days),
    }


def _build_structure(valued_schemes: list[tuple[str, str, str, float]]) -> dict | None:
    """`valued_schemes`: (scheme_name, amc_name, category, current_value)
    — one entry per matched, currently-valued holding. None if there's
    nothing to compute structure from (no holding has a usable current
    value yet), rather than a misleadingly empty-but-present breakdown."""
    if not valued_schemes:
        return None

    total_value = sum(v for _, _, _, v in valued_schemes)
    scheme_weights_pct = [(v / total_value) * 100 for _, _, _, v in valued_schemes]
    amc_items = [(amc, v) for _, amc, _, v in valued_schemes]
    category_items = [(cat, v) for _, _, cat, v in valued_schemes]
    asset_class_items = [(classify_asset_class(cat), v) for _, _, cat, v in valued_schemes]
    equity_style_items = [
        (classify_equity_style(cat), v) for _, _, cat, v in valued_schemes if classify_asset_class(cat) == "Equity"
    ]

    return {
        "scheme_concentration": _concentration_summary(scheme_weights_pct),
        "amc_concentration": _grouped_concentration(amc_items, total_value),
        "category_concentration": _grouped_concentration(category_items, total_value),
        "asset_allocation": _allocation_breakdown(asset_class_items, total_value),
        "equity_style_allocation": _allocation_breakdown(equity_style_items, total_value) if equity_style_items else [],
        "amc_allocation": _allocation_breakdown(amc_items, total_value),
        "category_allocation": _allocation_breakdown(category_items, total_value),
    }
