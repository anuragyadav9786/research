"""Builds the Portfolio Analysis Overview (invested capital, current
value, realized/unrealized gain, portfolio XIRR, per-scheme contribution,
holding-period analysis, time-weighted return/volatility/drawdown,
purchase/redemption behavior, SIP consistency, investment timing vs.
market conditions, investor behavior, and portfolio complexity) from a
CAS's full parsed transaction ledger — Phases 1-7 of the larger Portfolio
Analysis intelligence module (spec sections 4-5, 6, 12, 13, 14, 15).
Only covers schemes matched to this platform's own fund catalog by ISIN
(same matching cas_service.py already does for the manual-form pre-fill)
— a scheme not in our catalog has no NAV history we can use to value it
today, so it's reported as excluded, never guessed at.

Investor-behavior scope note: this deliberately does NOT attempt to
infer intent (e.g. "return-chasing" or "panic-selling" by correlating a
purchase/redemption date against recent NAV movement) — that would be an
unverifiable psychological claim about why the investor acted, not a
fact this ledger can establish, and risks exactly the alarmist,
judgmental framing the module's spec explicitly rules out. What's
reported instead (_investor_behavior_summary) is purely factual: how
long the recorded activity spans, and what fraction of invested capital
has since moved via a switch/STP or come back via a redemption/SWP/
dividend — observable amounts, not inferred motives.

Investment-timing note: the market regimes used to classify WHEN a
purchase happened (see _investment_timing_summary) are this platform's
own illustrative sample-data date windows, not verified real-world market
classifications — same caveat, and same METHODOLOGY_NOTE, as the
single-fund Market-Cycle Behaviour Engine (app/services/
market_regime_service.py) already carries. A purchase whose date falls
outside every known regime window is reported as unclassified, never
guessed into the nearest one.

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

import pandas as pd
from sqlalchemy.orm import Session

from analytics.concentration import group_weights, herfindahl_hirschman_index, hhi_label, top_n_weight_pct
from analytics.cost_basis import apply_fifo
from analytics.drawdown import max_drawdown
from analytics.portfolio import synthetic_nav_from_returns
from analytics.portfolio_valuation import (
    annualized_time_weighted_return,
    cash_flow_adjusted_returns,
    combine_portfolio_value_series,
    daily_net_contributions,
    time_weighted_return,
    units_held_series,
)
from analytics.risk import annualized_volatility
from analytics.xirr import xirr
from app.models.reference import MarketRegime, Scheme, SchemeVariant
from app.repositories import fund_repository, market_regime_repository
from app.schemas.market_regime import METHODOLOGY_NOTE as MARKET_REGIME_METHODOLOGY_NOTE
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

# Display order for the transaction-type activity breakdown -- external
# cash in, then external cash out, then internal transfers, then
# non-cash/other events. Any transaction_type the parser ever returns
# that isn't listed here still appears (appended, unordered) rather than
# silently dropped -- see _transaction_activity_summary.
_TRANSACTION_TYPE_DISPLAY_ORDER = [
    "PURCHASE",
    "SIP",
    "REDEMPTION",
    "SWP",
    "SWITCH_IN",
    "SWITCH_OUT",
    "STP_IN",
    "STP_OUT",
    "DIVIDEND",
    "DIVIDEND_REINVESTMENT",
    "BONUS",
    "REVERSAL",
    "OTHER",
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
    # Each priced scheme's own real (not static-weight) value-over-time
    # series, keyed by isin — the basis for the portfolio-wide TWR/
    # volatility/drawdown reconstruction. Only schemes with SOME NAV
    # history are included (a scheme we've never priced can't be placed
    # in a value series at all) — a broader set than valued_schemes above,
    # since a now-fully-redeemed scheme still contributed real historical
    # value along the way.
    priced_scheme_value_series: dict[str, pd.Series] = {}
    # (date, signed contribution) across every priced scheme — positive =
    # money the investor put in that day, negative = money taken out;
    # switches/STP excluded (internal, not a real external cash flow).
    priced_scheme_contributions: list[tuple[date, float]] = []
    # Every transaction belonging to a MATCHED scheme (priced or not) —
    # the basis for the portfolio-wide transaction-type activity
    # breakdown, which needs no pricing at all, just a count of what
    # actually happened.
    matched_transactions: list[CASTransaction] = []
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
        matched_transactions.extend(txns)
        cost_basis = apply_fifo([(t.transaction_date, t.units, t.amount) for t in txns])
        realized_holding_days.extend(c.holding_period_days for c in cost_basis.consumptions)

        nav_series = fund_repository.get_nav_series(db, variant.id)
        latest_nav = float(nav_series.iloc[-1]) if not nav_series.empty else None
        latest_nav_date = nav_series.index[-1].date() if not nav_series.empty else None
        current_value = cost_basis.remaining_units * latest_nav if latest_nav is not None else None
        unrealized_gain = current_value - cost_basis.remaining_cost if current_value is not None else None

        if not nav_series.empty:
            unit_events = [(t.transaction_date, t.units) for t in txns]
            priced_scheme_value_series[isin] = units_held_series(nav_series.index, unit_events) * nav_series
            for t in txns:
                if t.transaction_type in _OUTFLOW_TYPES:
                    priced_scheme_contributions.append((t.transaction_date, abs(t.amount)))
                elif t.transaction_type in _INFLOW_TYPES:
                    priced_scheme_contributions.append((t.transaction_date, -abs(t.amount)))

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
                "purchase_behavior": _purchase_behavior_summary(txns),
                "sip_consistency": _sip_consistency_summary(txns),
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
        "time_weighted_return": _time_weighted_return_summary(priced_scheme_value_series, priced_scheme_contributions),
        "transaction_activity": _transaction_activity_summary(matched_transactions),
        "investment_timing": _investment_timing_summary(matched_transactions, market_regime_repository.list_regimes(db)),
        "investor_behavior": _investor_behavior_summary(matched_transactions, total_invested),
        "complexity": _portfolio_complexity_summary(valued_schemes, matched_transactions),
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


def _time_weighted_return_summary(
    value_series_by_scheme: dict[str, pd.Series], contribution_events: list[tuple[date, float]]
) -> dict:
    """Portfolio Analysis §6: Time-Weighted Return, annualized volatility,
    and max drawdown of the portfolio's OWN actual value over time — not a
    single constituent fund's, and not a hypothetical fixed-weight blend
    (see analytics/portfolio_valuation.py's module docstring for why this
    differs from both). Only schemes with any NAV history at all can be
    placed in a value series, so a scheme this platform has never priced
    is excluded from this reconstruction entirely (both its value AND its
    cash flows) rather than partially included in a way that would show a
    misleading loss with no offsetting value. `priced_scheme_count` says
    how many of the matched schemes that reconstruction actually covers."""
    if not value_series_by_scheme:
        return {
            "cumulative_twr_pct": None,
            "annualized_twr_pct": None,
            "volatility_pct": None,
            "max_drawdown_pct": None,
            "drawdown_peak_date": None,
            "drawdown_trough_date": None,
            "drawdown_recovery_date": None,
            "drawdown_recovered": None,
            "priced_scheme_count": 0,
            "start_date": None,
            "end_date": None,
        }

    value = combine_portfolio_value_series(value_series_by_scheme)
    contributions = daily_net_contributions(value.index, contribution_events)
    returns = cash_flow_adjusted_returns(value, contributions)

    start_date = value.index[0].date() if not value.empty else None
    end_date = value.index[-1].date() if not value.empty else None

    cumulative_twr = time_weighted_return(returns)
    span_days = (end_date - start_date).days if start_date is not None and end_date is not None else 0
    # Annualizing a sub-year span amplifies noise into an absurd figure --
    # the same "meaningless for periods shorter than ~1 year" rule
    # analytics/returns.py's cagr() docstring documents, and the same
    # >= 1 year gate fund_analytics_service.py's rolling-returns windows
    # already use. cumulative_twr_pct (the actual, un-annualized return
    # over the real span) is always reported regardless.
    annualized_twr = (
        annualized_time_weighted_return(cumulative_twr, start_date, end_date)
        if cumulative_twr is not None and span_days >= 365
        else None
    )
    volatility = annualized_volatility(returns) if len(returns) >= 2 else None

    dd = None
    if len(returns) >= 1:
        synthetic_nav = synthetic_nav_from_returns(returns)
        if len(synthetic_nav) >= 2:
            dd = max_drawdown(synthetic_nav)

    return {
        "cumulative_twr_pct": round(cumulative_twr * 100, 2) if cumulative_twr is not None else None,
        "annualized_twr_pct": round(annualized_twr * 100, 2) if annualized_twr is not None else None,
        "volatility_pct": round(volatility * 100, 2) if volatility is not None else None,
        "max_drawdown_pct": round(dd["max_drawdown_pct"] * 100, 2) if dd is not None else None,
        "drawdown_peak_date": dd["peak_date"].date() if dd is not None else None,
        "drawdown_trough_date": dd["trough_date"].date() if dd is not None else None,
        "drawdown_recovery_date": (
            dd["recovery_date"].date() if dd is not None and dd["recovery_date"] is not None else None
        ),
        "drawdown_recovered": dd["recovered"] if dd is not None else None,
        "priced_scheme_count": len(value_series_by_scheme),
        "start_date": start_date,
        "end_date": end_date,
    }


def _purchase_behavior_summary(txns: list[CASTransaction]) -> dict:
    """Portfolio Analysis §13: this scheme's own purchase/NAV behavior —
    how many purchases were made, lumpsum vs. SIP, over what span, and at
    what NAV range. Uses amount/units (not the transaction row's own
    separately-reported Price column) for the price actually paid on each
    purchase, the same convention analytics/cost_basis.py's cost-basis
    already uses, so this never disagrees with the cost-basis figures
    shown alongside it. Purely descriptive: reports what happened, not
    whether it was good or bad timing."""
    purchases = [t for t in txns if t.transaction_type in _OUTFLOW_TYPES]
    if not purchases:
        return {
            "purchase_count": 0,
            "sip_installment_count": 0,
            "lumpsum_count": 0,
            "first_purchase_date": None,
            "latest_purchase_date": None,
            "lowest_purchase_nav": None,
            "highest_purchase_nav": None,
            "average_purchase_nav": None,
        }

    prices_paid = [t.amount / t.units for t in purchases if t.units]
    total_amount = sum(t.amount for t in purchases)
    total_units = sum(t.units for t in purchases)
    purchase_dates = [t.transaction_date for t in purchases]

    return {
        "purchase_count": len(purchases),
        "sip_installment_count": sum(1 for t in purchases if t.transaction_type == "SIP"),
        "lumpsum_count": sum(1 for t in purchases if t.transaction_type == "PURCHASE"),
        "first_purchase_date": min(purchase_dates),
        "latest_purchase_date": max(purchase_dates),
        "lowest_purchase_nav": round(min(prices_paid), 4) if prices_paid else None,
        "highest_purchase_nav": round(max(prices_paid), 4) if prices_paid else None,
        "average_purchase_nav": round(total_amount / total_units, 4) if total_units else None,
    }


def _sip_consistency_summary(txns: list[CASTransaction]) -> dict | None:
    """Portfolio Analysis §13: how regularly this scheme's SIP installments
    actually arrived — purely from the gaps between consecutive
    installment dates, never from an assumed "should be monthly" cadence
    (the CAS itself doesn't state the registered SIP frequency, so
    guessing one and calling installments "missed" against it would be
    fabricating a claim we can't verify). None if this scheme has no SIP
    installments at all, so a lumpsum-only scheme doesn't get a
    misleadingly empty SIP card.

    `gap_consistency_pct`: 100 * (1 - min(coefficient_of_variation, 1)),
    where coefficient_of_variation = population_stdev(gaps) / mean(gaps).
    100 = every gap was identical; 0 = gaps varied by as much as (or more
    than) their own average. A simple, fully transparent dispersion
    measure — not a standard finance metric, and not a judgment of good
    or bad investing behavior."""
    sip_dates = sorted(t.transaction_date for t in txns if t.transaction_type == "SIP")
    if not sip_dates:
        return None

    installment_count = len(sip_dates)
    if installment_count < 2:
        return {
            "installment_count": installment_count,
            "first_installment_date": sip_dates[0],
            "latest_installment_date": sip_dates[0],
            "average_gap_days": None,
            "min_gap_days": None,
            "max_gap_days": None,
            "gap_consistency_pct": None,
        }

    gaps = [(sip_dates[i + 1] - sip_dates[i]).days for i in range(installment_count - 1)]
    mean_gap = statistics.mean(gaps)
    coefficient_of_variation = (statistics.pstdev(gaps) / mean_gap) if mean_gap > 0 else 0.0

    return {
        "installment_count": installment_count,
        "first_installment_date": sip_dates[0],
        "latest_installment_date": sip_dates[-1],
        "average_gap_days": round(mean_gap, 1),
        "min_gap_days": min(gaps),
        "max_gap_days": max(gaps),
        "gap_consistency_pct": round(max(0.0, 1.0 - min(coefficient_of_variation, 1.0)) * 100, 1),
    }


def _matching_regime(purchase_date: date, regimes: list[MarketRegime]) -> MarketRegime | None:
    for regime in regimes:
        if purchase_date >= regime.start_date and (regime.end_date is None or purchase_date <= regime.end_date):
            return regime
    return None


def _investment_timing_summary(matched_transactions: list[CASTransaction], regimes: list[MarketRegime]) -> dict:
    """Portfolio Analysis §14: how much money went in during each known
    market regime (bull/correction/high-volatility/etc.) — purely
    descriptive, never a claim about whether the timing was good or bad.
    Regimes come from this platform's own market_regimes reference table,
    the same source and same illustrative-sample-data caveat
    (`methodology_note`) the single-fund Market-Cycle Behaviour Engine
    already carries — see this module's own docstring. A purchase dated
    outside every known regime window is reported separately as
    unclassified, never guessed into the nearest one."""
    purchases = [t for t in matched_transactions if t.transaction_type in _OUTFLOW_TYPES]

    by_regime: dict[int, dict] = {}
    unclassified_amount = 0.0
    unclassified_count = 0

    for t in purchases:
        regime = _matching_regime(t.transaction_date, regimes)
        if regime is None:
            unclassified_amount += t.amount
            unclassified_count += 1
            continue
        bucket = by_regime.setdefault(
            regime.id, {"regime_name": regime.name, "regime_type": regime.regime_type, "invested_amount": 0.0, "purchase_count": 0}
        )
        bucket["invested_amount"] += t.amount
        bucket["purchase_count"] += 1

    total_classified = sum(b["invested_amount"] for b in by_regime.values())
    regime_breakdown = [
        {
            **{k: v for k, v in bucket.items() if k != "invested_amount"},
            "invested_amount": round(bucket["invested_amount"], 2),
            "weight_pct": round((bucket["invested_amount"] / total_classified) * 100, 2) if total_classified > 0 else 0.0,
        }
        for bucket in sorted(by_regime.values(), key=lambda b: b["invested_amount"], reverse=True)
    ]

    return {
        "regime_breakdown": regime_breakdown,
        "total_classified_invested_amount": round(total_classified, 2),
        "unclassified_invested_amount": round(unclassified_amount, 2),
        "unclassified_purchase_count": unclassified_count,
        "methodology_note": MARKET_REGIME_METHODOLOGY_NOTE,
    }


def _transaction_activity_summary(matched_transactions: list[CASTransaction]) -> list[dict]:
    """Portfolio Analysis §14: how often, and for how much, the investor
    actually redeemed, switched, or otherwise transacted — a breakdown by
    transaction_type across every MATCHED scheme (pricing not required,
    since this only counts what happened, not what it's now worth).
    Purely descriptive: no framing of any category as good or bad, and no
    row for a type that never occurred, rather than a padded list of
    zeros."""
    totals: dict[str, dict] = {}
    for t in matched_transactions:
        bucket = totals.setdefault(t.transaction_type, {"count": 0, "total_amount": 0.0})
        bucket["count"] += 1
        bucket["total_amount"] += abs(t.amount)

    ordered_types = _TRANSACTION_TYPE_DISPLAY_ORDER + [t for t in totals if t not in _TRANSACTION_TYPE_DISPLAY_ORDER]
    return [
        {"transaction_type": ttype, "count": totals[ttype]["count"], "total_amount": round(totals[ttype]["total_amount"], 2)}
        for ttype in ordered_types
        if ttype in totals
    ]


# Internal transfer out of a scheme -- a real move of money between two
# holdings within this same portfolio, never a claim about why.
_INTERNAL_TRANSFER_OUT_TYPES = {"SWITCH_OUT", "STP_OUT"}


def _investor_behavior_summary(matched_transactions: list[CASTransaction], total_invested: float) -> dict:
    """Portfolio Analysis §14: purely factual investor-behavior metrics —
    how long the recorded activity spans, and what fraction of invested
    capital has since moved via a switch/STP or come back via a
    redemption/SWP/dividend. Deliberately excludes any inference about
    WHY (e.g. "return-chasing," "panic-selling") — see this module's own
    docstring. `investing_span_days` is between the first and last
    transaction actually in this ledger, not against today's date (the
    statement may be stale), so it describes recorded activity, not a
    live "years invested" claim."""
    if not matched_transactions:
        return {
            "investing_since": None,
            "last_activity_date": None,
            "investing_span_days": None,
            "total_switched_amount": 0.0,
            "switch_ratio_pct": None,
            "total_redeemed_amount": 0.0,
            "redemption_ratio_pct": None,
        }

    dates = [t.transaction_date for t in matched_transactions]
    investing_since = min(dates)
    last_activity_date = max(dates)

    total_switched = sum(abs(t.amount) for t in matched_transactions if t.transaction_type in _INTERNAL_TRANSFER_OUT_TYPES)
    total_redeemed = sum(abs(t.amount) for t in matched_transactions if t.transaction_type in _INFLOW_TYPES)

    return {
        "investing_since": investing_since,
        "last_activity_date": last_activity_date,
        "investing_span_days": (last_activity_date - investing_since).days,
        "total_switched_amount": round(total_switched, 2),
        "switch_ratio_pct": round((total_switched / total_invested) * 100, 2) if total_invested > 0 else None,
        "total_redeemed_amount": round(total_redeemed, 2),
        "redemption_ratio_pct": round((total_redeemed / total_invested) * 100, 2) if total_invested > 0 else None,
    }


# (label, max_scheme_count) in order; None = unbounded (last label). The
# single clearest driver of how much an investor has to actively track.
_COMPLEXITY_LABELS: list[tuple[str, int | None]] = [
    ("Simple", 3),
    ("Moderate", 7),
    ("Complex", 12),
    ("Highly Complex", None),
]


def _portfolio_complexity_summary(
    valued_schemes: list[tuple[str, str, str, float]], matched_transactions: list[CASTransaction]
) -> dict:
    """Portfolio Analysis §complexity: how many distinct moving parts this
    portfolio's CURRENT holdings actually span — same `valued_schemes`
    basis as Portfolio Structure above, so the two sections stay
    consistent. `folio_count` is a genuinely separate signal this
    platform doesn't surface anywhere else: the same scheme registered
    under two different folios is silently merged into one scheme
    elsewhere in this overview (matched by ISIN), so two folios for one
    fund would otherwise be invisible.

    `complexity_score`: min(100, scheme_count*6 + amc_count*4 +
    category_count*3 + max(0, folio_count - scheme_count)*8) — a simple,
    fully transparent, explicitly documented heuristic combining scheme/
    AMC/category count plus any folio duplication, not a standard
    industry index and not a judgment of whether that complexity is a
    problem. `complexity_label` is thresholded on scheme_count alone (the
    clearest single driver) so it stays interpretable on its own even
    without the score."""
    scheme_count = len(valued_schemes)
    amc_count = len({amc for _, amc, _, _ in valued_schemes})
    category_count = len({cat for _, _, cat, _ in valued_schemes})
    asset_class_count = len({classify_asset_class(cat) for _, _, cat, _ in valued_schemes})
    folio_count = len({t.folio_no for t in matched_transactions if t.folio_no})

    complexity_score = min(
        100,
        scheme_count * 6 + amc_count * 4 + category_count * 3 + max(0, folio_count - scheme_count) * 8,
    )
    complexity_label = next(
        label for label, max_count in _COMPLEXITY_LABELS if max_count is None or scheme_count <= max_count
    )

    return {
        "scheme_count": scheme_count,
        "amc_count": amc_count,
        "category_count": category_count,
        "asset_class_count": asset_class_count,
        "folio_count": folio_count,
        "complexity_score": complexity_score,
        "complexity_label": complexity_label,
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
