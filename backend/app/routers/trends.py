from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db import get_db_session
from app.services.langgraph_router import compute_trend_payload

router = APIRouter(prefix="/api")

@router.get("/trends")
def get_trends(
    group_by: str = Query("district", regex="^(district|crime_type|month)$"),
    district: Optional[str] = None,
    crime_type: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    filters = {
        "district": district,
        "crime_type": crime_type
    }
    payload = compute_trend_payload(filters, db, group_by=group_by)
    return payload
