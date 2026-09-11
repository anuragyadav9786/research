from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — deliberately broad for a health probe
        db_status = "unreachable"

    return {"status": "ok", "database": db_status}
