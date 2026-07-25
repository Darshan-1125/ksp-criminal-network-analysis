from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db import get_db_session
from app.models import AuditLog
from app.services.langgraph_router import compute_trend_payload
from app.services.auth_service import require_role

router = APIRouter(prefix="/api")

ALLOWED_TREND_ROLES = ["admin", "supervisor", "investigator", "analyst", "policymaker", "read_only"]

@router.get("/trends")
def get_trends(
    group_by: str = Query("district", regex="^(district|crime_type|month)$"),
    district: Optional[str] = None,
    crime_type: Optional[str] = None,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(ALLOWED_TREND_ROLES))
):
    filters = {
        "district": district,
        "crime_type": crime_type
    }
    payload = compute_trend_payload(filters, db, group_by=group_by)

    # Audit Log Recording
    try:
        data_points = len(payload.get("data", [])) if isinstance(payload, dict) else 0
        log_entry = AuditLog(
            user_id=current_user.get("id"),
            username=current_user.get("username"),
            role=current_user.get("role"),
            method="GET",
            endpoint="/api/trends",
            status_code=200,
            query_text=f"trends query: group_by={group_by}, district={district}, crime={crime_type}",
            returned_records={"group_by": group_by, "data_points": data_points}
        )
        db.add(log_entry)
        db.commit()
    except Exception:
        db.rollback()

    return payload
