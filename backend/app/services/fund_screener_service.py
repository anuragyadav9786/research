"""Fund screener — reads only the precomputed fund_period_returns table
(data_pipeline/orchestration/period_return_rollup.py's daily rollup),
never recomputes live, same "serve from the cache, don't recalculate"
convention fund_metrics/GET /funds/{id}/risk already use.

A transparent, sortable table of real returns — not a ranking (see
FundScreenerResponse's docstring).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reference import AMC, FundFamily, Scheme, SchemeVariant
from app.models.timeseries import FundPeriodReturn
from app.schemas.funds import SCREENER_PERIODS

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def get_fund_screener(db: Session, sort_by: str, sort_dir: str, limit: int) -> dict:
    limit = max(1, min(limit, MAX_LIMIT))

    rows = db.execute(
        select(
            Scheme.id,
            Scheme.name,
            Scheme.category,
            AMC.name,
            FundPeriodReturn.period,
            FundPeriodReturn.return_pct,
            FundPeriodReturn.as_of_date,
            FundPeriodReturn.anchor_date,
        )
        .select_from(FundPeriodReturn)
        .join(SchemeVariant, SchemeVariant.id == FundPeriodReturn.scheme_variant_id)
        .join(Scheme, Scheme.id == SchemeVariant.scheme_id)
        .join(FundFamily, FundFamily.id == Scheme.fund_family_id)
        .join(AMC, AMC.id == FundFamily.amc_id)
    ).all()

    as_of_date = None
    by_fund: dict[int, dict] = {}
    for fund_id, scheme_name, category, amc_name, period, return_pct, row_as_of, anchor_date in rows:
        if as_of_date is None or row_as_of > as_of_date:
            as_of_date = row_as_of
        entry = by_fund.setdefault(
            fund_id,
            {"id": fund_id, "scheme_name": scheme_name, "category": category, "amc_name": amc_name, "returns": {}},
        )
        entry["returns"][period] = {
            "return_pct": float(return_pct),
            "status": "VALID",
            "anchor_date": anchor_date,
        }

    # Every eligible fund gets an entry for every period, even one with no
    # computed row (e.g. not enough history for 5y yet) — DATA_UNAVAILABLE,
    # never silently absent from the response.
    for entry in by_fund.values():
        for period in SCREENER_PERIODS:
            entry["returns"].setdefault(period, {"return_pct": None, "status": "DATA_UNAVAILABLE", "anchor_date": None})

    items = list(by_fund.values())

    def _sort_key(entry: dict) -> tuple[int, float]:
        value = entry["returns"].get(sort_by, {}).get("return_pct")
        if value is None:
            # Missing values always sort last, regardless of direction —
            # a fund with no computable return for this period shouldn't
            # appear to "win" an ascending sort just because it's absent.
            return (1, 0.0)
        return (0, -value if sort_dir == "desc" else value)

    items.sort(key=_sort_key)

    return {
        "as_of_date": as_of_date,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "total_eligible": len(by_fund),
        "items": items[:limit],
    }
