"""Portfolio Analysis §"what changed over time": diffs two already-parsed
CAS statements — an earlier one and a later one — to show what actually
changed between them.

Architectural note (why this takes two uploads instead of remembering
one): this platform has no accounts or auth (see app/schemas/
portfolio_analysis.py's own docstring on why multi-fund analysis is
stateless), so there is nothing to persist a "my portfolio, last seen"
record against, and no session boundary to protect it behind if there
were. Comparing two statements the investor uploads together — same as
every other CAS feature, one request in, one computed response out —
needs no new persistence, no account model, and stores nothing.

Everything here is pure dict-diffing over two already-built
build_cas_overview() results (app/services/cas_portfolio_service.py) —
no new financial calculations, since "what changed" is just arithmetic
on numbers those functions already compute correctly.

Pricing-convention note (why this isolates YOUR behavior, not the
market's): build_cas_overview's own current_value/total_current_value
always price whatever units a statement's ledger shows as held at
today's LATEST known NAV — the same convention used everywhere else in
this module, never the NAV as of that statement's own generation date.
So a value/gain difference between the two snapshots here is driven by
what actually changed in your unit holdings and cost basis (new
purchases, redemptions, switches) between the two statements, not by
market movement in between — that's what XIRR/TWR already measure
elsewhere. Comparing "your holdings, both priced today" is what makes
this a clean "what did you actually do differently" read rather than a
number that conflates your behavior with the market's.
"""
from __future__ import annotations

from datetime import date

_VALUED_SCHEME_MIN = 0.0  # a scheme counts as "held" in a snapshot if current_value > this


def _valued_schemes_by_isin(overview: dict) -> dict[str, dict]:
    return {
        s["isin"]: s
        for s in overview["per_scheme"]
        if s["current_value"] is not None and s["current_value"] > _VALUED_SCHEME_MIN
    }


def _allocation_weights(structure: dict | None) -> dict[str, float]:
    if structure is None:
        return {}
    return {s["label"]: s["weight_pct"] for s in structure["asset_allocation"]}


def _allocation_drift(previous_structure: dict | None, current_structure: dict | None) -> list[dict]:
    previous_weights = _allocation_weights(previous_structure)
    current_weights = _allocation_weights(current_structure)
    labels = set(previous_weights) | set(current_weights)

    drift = [
        {
            "label": label,
            "previous_weight_pct": round(previous_weights.get(label, 0.0), 2),
            "current_weight_pct": round(current_weights.get(label, 0.0), 2),
            "weight_pct_change": round(current_weights.get(label, 0.0) - previous_weights.get(label, 0.0), 2),
        }
        for label in labels
    ]
    return sorted(drift, key=lambda d: abs(d["weight_pct_change"]), reverse=True)


def compare_cas_overviews(
    previous_as_of_date: date | None,
    previous_overview: dict,
    current_as_of_date: date | None,
    current_overview: dict,
) -> dict:
    """`previous_overview`/`current_overview`: full build_cas_overview()
    results, already computed by the caller (never recomputed here).
    Schemes are matched across the two snapshots by ISIN — the same
    stable identity key used throughout the rest of the CAS module.
    "New" and "exited" are relative to which snapshot the scheme has a
    usable current_value > 0 in, not merely whether its ISIN appears in
    the transaction ledger (an unpriced or fully-redeemed scheme isn't
    "new" just because we can price it now)."""
    previous_by_isin = _valued_schemes_by_isin(previous_overview)
    current_by_isin = _valued_schemes_by_isin(current_overview)

    new_isins = set(current_by_isin) - set(previous_by_isin)
    exited_isins = set(previous_by_isin) - set(current_by_isin)
    common_isins = set(previous_by_isin) & set(current_by_isin)

    new_schemes = [
        {
            "fund_id": current_by_isin[isin]["fund_id"],
            "scheme_name": current_by_isin[isin]["scheme_name"],
            "isin": isin,
            "current_value": current_by_isin[isin]["current_value"],
        }
        for isin in new_isins
    ]
    exited_schemes = [
        {
            "fund_id": previous_by_isin[isin]["fund_id"],
            "scheme_name": previous_by_isin[isin]["scheme_name"],
            "isin": isin,
            "previous_value": previous_by_isin[isin]["current_value"],
        }
        for isin in exited_isins
    ]
    scheme_changes = [
        {
            "fund_id": current_by_isin[isin]["fund_id"],
            "scheme_name": current_by_isin[isin]["scheme_name"],
            "isin": isin,
            "previous_value": previous_by_isin[isin]["current_value"],
            "current_value": current_by_isin[isin]["current_value"],
            "value_change": round(current_by_isin[isin]["current_value"] - previous_by_isin[isin]["current_value"], 2),
            "previous_weight_pct": previous_by_isin[isin]["weight_pct"],
            "current_weight_pct": current_by_isin[isin]["weight_pct"],
            "weight_pct_change": (
                round(current_by_isin[isin]["weight_pct"] - previous_by_isin[isin]["weight_pct"], 2)
                if previous_by_isin[isin]["weight_pct"] is not None and current_by_isin[isin]["weight_pct"] is not None
                else None
            ),
        }
        for isin in common_isins
    ]
    scheme_changes.sort(key=lambda c: abs(c["value_change"]), reverse=True)

    span_days = (
        (current_as_of_date - previous_as_of_date).days
        if previous_as_of_date is not None and current_as_of_date is not None
        else None
    )

    return {
        "previous_as_of_date": previous_as_of_date,
        "current_as_of_date": current_as_of_date,
        "span_days": span_days,
        "total_invested_previous": previous_overview["total_invested"],
        "total_invested_current": current_overview["total_invested"],
        "total_invested_change": round(current_overview["total_invested"] - previous_overview["total_invested"], 2),
        "total_current_value_previous": previous_overview["total_current_value"],
        "total_current_value_current": current_overview["total_current_value"],
        "total_current_value_change": round(
            current_overview["total_current_value"] - previous_overview["total_current_value"], 2
        ),
        "total_gain_previous": previous_overview["total_gain"],
        "total_gain_current": current_overview["total_gain"],
        "total_gain_change": round(current_overview["total_gain"] - previous_overview["total_gain"], 2),
        "portfolio_xirr_pct_previous": previous_overview["portfolio_xirr_pct"],
        "portfolio_xirr_pct_current": current_overview["portfolio_xirr_pct"],
        "new_schemes": sorted(new_schemes, key=lambda s: s["current_value"], reverse=True),
        "exited_schemes": sorted(exited_schemes, key=lambda s: s["previous_value"], reverse=True),
        "scheme_changes": scheme_changes,
        "asset_allocation_drift": _allocation_drift(previous_overview["structure"], current_overview["structure"]),
    }
