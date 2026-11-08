"""Cross-fund security lookup -- "which schemes (across any AMC) hold
this security, and at what weight" -- the natural follow-on question
once holdings span more than one AMC with real ISIN overlap, and a
genuinely new capability (no endpoint for this existed before).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories import security_repository
from app.schemas.security import HolderRow, SecurityHoldersResponse, SecuritySearchResponse, SecuritySummary

router = APIRouter(prefix="/api/securities", tags=["securities"])


def _security_summary(db: Session, security) -> SecuritySummary:
    return SecuritySummary(
        id=security.id,
        name=security.name,
        isin=security.isin,
        instrument_type=security.instrument_type,
        sector=security_repository.get_security_sector_name(db, security),
    )


@router.get("/search", response_model=SecuritySearchResponse)
def search_securities(q: str = Query(..., min_length=1), db: Session = Depends(get_db)) -> dict:
    securities = security_repository.search_securities(db, q)
    return {"items": [_security_summary(db, s) for s in securities]}


@router.get("/{security_id}/holders", response_model=SecurityHoldersResponse)
def get_security_holders(security_id: int, db: Session = Depends(get_db)) -> dict:
    security = security_repository.get_security(db, security_id)
    if security is None:
        raise HTTPException(status_code=404, detail=f"Security {security_id} not found")

    holders = security_repository.get_holders(db, security_id)
    return {
        "security": _security_summary(db, security),
        "holders": [
            HolderRow(
                scheme_id=h.scheme_id,
                scheme_name=h.scheme_name,
                amc_name=h.amc_name,
                as_of_date=h.as_of_date,
                weight_pct=h.weight_pct,
                market_value=h.market_value,
            )
            for h in holders
        ],
        "total_holders": len(holders),
    }
