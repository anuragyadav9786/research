"""Multi-fund Portfolio Analysis API — Phase 9.

POST /api/portfolio/analyse (Section 20's listed endpoint): given a
hypothetical set of funds and their weights in a portfolio, computes
combined ("look-through") holdings, sector/market-cap allocation,
concentration, pairwise overlap between constituents, and portfolio-level
risk/drawdown — all built from the existing single-fund analytics engines,
never a new ad hoc calculation duplicating them.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from analytics.concentration import group_weights
from analytics.returns import returns_series
from app.core.config import get_settings
from app.core.database import get_db
from app.repositories import fund_repository, portfolio_repository
from app.schemas.cas import CASComparisonResponse, CASParseResponse
from app.schemas.portfolio_analysis import PortfolioAnalyseRequest, PortfolioAnalysisResponse
from app.services import cas_comparison_service, cas_service, portfolio_analysis_service
from data_pipeline.normalization.cas_pdf import CASPasswordError, CASUnreadableError, extract_cas_text

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

WEIGHT_SUM_TOLERANCE_PCT = 0.5
UNCLASSIFIED_LABEL = "unclassified"
MAX_CAS_FILE_SIZE_BYTES = 5 * 1024 * 1024  # matches the upload UI's own "Max 5 MB" limit


@router.post("/analyse", response_model=PortfolioAnalysisResponse)
def analyse_portfolio(request: PortfolioAnalyseRequest, db: Session = Depends(get_db)) -> dict:
    fund_ids = [h.fund_id for h in request.holdings]
    if len(fund_ids) != len(set(fund_ids)):
        raise HTTPException(status_code=400, detail="Duplicate fund_id in holdings")

    total_weight = sum(h.weight_pct for h in request.holdings)
    if abs(total_weight - 100.0) > WEIGHT_SUM_TOLERANCE_PCT:
        raise HTTPException(
            status_code=400,
            detail=f"holdings weight_pct must sum to ~100% (got {total_weight:.2f}%)",
        )

    fund_weights_pct = {h.fund_id: h.weight_pct for h in request.holdings}
    fund_names: dict[int, str] = {}
    per_fund_security_weights: dict[int, dict[str, float]] = {}
    per_fund_sector_weights: dict[int, dict[str, float]] = {}
    per_fund_mktcap_weights: dict[int, dict[str, float]] = {}
    per_fund_returns = {}

    for fund_id in fund_ids:
        scheme = fund_repository.get_scheme(db, fund_id)
        if scheme is None:
            raise HTTPException(status_code=404, detail=f"Fund {fund_id} not found")
        fund_names[fund_id] = scheme.name

        snapshot = portfolio_repository.get_latest_snapshot(db, scheme.id)
        if snapshot is not None:
            holdings = portfolio_repository.get_holdings(db, snapshot.id)
            per_fund_security_weights[fund_id] = {h.security_name: h.weight_pct for h in holdings}
            per_fund_sector_weights[fund_id] = group_weights(
                [(h.sector_name or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings]
            )
            per_fund_mktcap_weights[fund_id] = group_weights(
                [(h.market_cap_category or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings]
            )

        variant = fund_repository.get_default_variant(db, scheme.id)
        if variant is not None:
            nav = fund_repository.get_nav_series(db, variant.id)
            if not nav.empty:
                per_fund_returns[fund_id] = returns_series(nav)

    risk_free_rate = get_settings().risk_free_rate
    return portfolio_analysis_service.compute_portfolio_analysis(
        fund_names=fund_names,
        fund_weights_pct=fund_weights_pct,
        per_fund_security_weights=per_fund_security_weights,
        per_fund_sector_weights=per_fund_sector_weights,
        per_fund_mktcap_weights=per_fund_mktcap_weights,
        per_fund_returns=per_fund_returns,
        risk_free_rate_annual=risk_free_rate,
    )


async def _parse_cas_upload(file: UploadFile, password: str | None, db: Session, *, label: str) -> dict:
    """Shared by /cas/parse and /cas/compare — extract, decrypt, and parse
    one uploaded CAS PDF into a full CASParseResponse-shaped dict. `label`
    ("statement" / "previous statement" / "current statement") only
    changes error text, so a two-file request can tell the caller which
    of the two files was the problem."""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=422, detail=f"Upload a PDF file for the {label}.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_CAS_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"The {label} is too large — maximum 5 MB.")

    try:
        text = extract_cas_text(pdf_bytes, password)
    except CASPasswordError as exc:
        raise HTTPException(status_code=422, detail=f"{label.capitalize()}: {exc}") from exc
    except CASUnreadableError as exc:
        raise HTTPException(status_code=422, detail=f"{label.capitalize()}: {exc}") from exc

    result = cas_service.build_cas_parse_response(db, text)
    if not result["matched_holdings"] and not result["unmatched_holdings"]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not find any currently-held mutual fund positions in the {label}. "
                "Make sure this is a CAMS/KFintech Consolidated Account Statement PDF."
            ),
        )
    return result


@router.post("/cas/parse", response_model=CASParseResponse)
async def parse_cas_statement(
    file: UploadFile = File(...),
    password: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    """Upload a CAS (Consolidated Account Statement) PDF and get back the
    currently-held mutual fund positions it states, matched to this
    platform's own fund catalog by ISIN — a pre-fill for /analyse, not a
    replacement for it (the caller still submits the usual holdings list,
    just populated from here instead of typed by hand)."""
    return await _parse_cas_upload(file, password, db, label="statement")


@router.post("/cas/compare", response_model=CASComparisonResponse)
async def compare_cas_statements(
    previous_file: UploadFile = File(...),
    previous_password: str | None = Form(None),
    current_file: UploadFile = File(...),
    current_password: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    """Upload two CAS statements from different dates and see what
    changed between them — new/exited holdings, value and weight
    movement per scheme, and asset-allocation drift. Stateless: nothing
    from either statement is persisted (see app/services/
    cas_comparison_service.py's own docstring on why this takes two
    uploads rather than remembering one). If the two files are supplied
    in the wrong order (the "previous" one is actually more recent), they
    are swapped automatically — `dates_swapped` in the response says so —
    rather than producing a nonsensical "you divested everything" diff."""
    previous = await _parse_cas_upload(previous_file, previous_password, db, label="previous statement")
    current = await _parse_cas_upload(current_file, current_password, db, label="current statement")

    previous_as_of = previous["as_of_date"]
    current_as_of = current["as_of_date"]
    dates_swapped = False
    if previous_as_of is not None and current_as_of is not None and previous_as_of > current_as_of:
        previous, current = current, previous
        previous_as_of, current_as_of = current_as_of, previous_as_of
        dates_swapped = True

    comparison = cas_comparison_service.compare_cas_overviews(
        previous_as_of, previous["overview"], current_as_of, current["overview"]
    )
    return {
        **comparison,
        "dates_swapped": dates_swapped,
        "previous_unmatched_schemes": previous["overview"]["unmatched_schemes"],
        "current_unmatched_schemes": current["overview"]["unmatched_schemes"],
    }
