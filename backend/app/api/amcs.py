"""AMC/fund-family browsing — closes the gap where AMC was only ever a
free-text filter on scheme search (fund_repository.list_schemes' amc_name
param), with no dedicated page/endpoint of its own.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories import amc_repository
from app.schemas.amc import AmcDetailResponse, AmcListResponse, AmcSchemeRow, AmcSummary

router = APIRouter(prefix="/api/amcs", tags=["amcs"])


@router.get("", response_model=AmcListResponse)
def list_amcs(db: Session = Depends(get_db)) -> dict:
    rows = amc_repository.list_amcs(db)
    return {
        "items": [
            AmcSummary(
                id=r.id,
                name=r.name,
                fund_family_count=r.fund_family_count,
                scheme_count=r.scheme_count,
                schemes_with_holdings_count=r.schemes_with_holdings_count,
            )
            for r in rows
        ]
    }


@router.get("/{amc_id}", response_model=AmcDetailResponse)
def get_amc_detail(amc_id: int, db: Session = Depends(get_db)) -> dict:
    amc = amc_repository.get_amc(db, amc_id)
    if amc is None:
        raise HTTPException(status_code=404, detail=f"AMC {amc_id} not found")

    schemes = amc_repository.list_schemes_for_amc(db, amc_id)
    return {
        "id": amc.id,
        "name": amc.name,
        "schemes": [
            AmcSchemeRow(
                id=s.id,
                scheme_name=s.scheme_name,
                category=s.category,
                fund_family_name=s.fund_family_name,
                benchmark_name=s.benchmark_name,
                holdings_as_of_date=s.holdings_as_of_date,
            )
            for s in schemes
        ],
    }
