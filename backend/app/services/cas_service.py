"""Matches parsed CAS holdings (data_pipeline/normalization/cas_parser.py)
against this platform's own fund catalog, by ISIN — the same identifier
the CAS itself states, and already a unique column on SchemeVariant, so
this is a direct lookup, never a fuzzy name match. A holding whose ISIN
isn't in our database is reported as unmatched, not dropped silently or
substituted with a guess.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.reference import Scheme, SchemeVariant
from app.services.cas_portfolio_service import build_cas_overview
from data_pipeline.normalization.cas_parser import parse_cas_text, statement_end_date


def build_cas_parse_response(db: Session, text: str) -> dict:
    parsed = parse_cas_text(text)
    holdings = parsed.holdings
    as_of_date = statement_end_date(text)

    matched: list[dict] = []
    unmatched: list[dict] = []

    isins = [h.isin for h in holdings]
    variants_by_isin: dict[str, SchemeVariant] = {}
    if isins:
        rows = (
            db.query(SchemeVariant, Scheme)
            .join(Scheme, SchemeVariant.scheme_id == Scheme.id)
            .filter(SchemeVariant.isin.in_(isins))
            .all()
        )
        for variant, scheme in rows:
            variants_by_isin[variant.isin] = (variant, scheme)

    for holding in holdings:
        found = variants_by_isin.get(holding.isin)
        if found is None:
            unmatched.append(
                {
                    "scheme_name": holding.scheme_name or holding.isin,
                    "isin": holding.isin,
                    "market_value": holding.market_value,
                    "reason": "isin_not_found",
                }
            )
            continue
        _variant, scheme = found
        matched.append(
            {
                "fund_id": scheme.id,
                "scheme_name": scheme.name,
                "isin": holding.isin,
                "market_value": holding.market_value,
            }
        )

    matched_market_value = sum(m["market_value"] for m in matched)
    for m in matched:
        m["weight_pct"] = round((m["market_value"] / matched_market_value) * 100, 4) if matched_market_value > 0 else 0.0

    total_market_value = round(sum(h.market_value for h in holdings), 2)

    return {
        "as_of_date": as_of_date,
        "matched_holdings": matched,
        "unmatched_holdings": unmatched,
        "total_market_value": total_market_value,
        "matched_market_value": round(matched_market_value, 2),
        "overview": build_cas_overview(db, parsed.transactions),
    }
