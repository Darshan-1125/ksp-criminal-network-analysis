from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db import get_db_session
from app.models import FIRCase, District, Accused, AuditLog
from app.services.db_service import search_cases_structured, get_case_by_id
from app.services.auth_service import require_role

router = APIRouter(prefix="/api")

ALLOWED_CASES_ROLES = ["admin", "supervisor", "investigator", "analyst", "read_only"]

@router.get("/cases")
def get_cases(
    crime_type: Optional[str] = None,
    district: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    accused_name: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(ALLOWED_CASES_ROLES))
):
    filters = {
        "crime_type": crime_type,
        "district": district,
        "date_from": date_from,
        "date_to": date_to,
        "accused_name": accused_name,
        "limit": limit,
        "offset": offset
    }
    
    search_res = search_cases_structured(filters)
    total = search_res.get("total_count", 0)
    results = search_res.get("cases", [])

    # Log audit entry
    try:
        returned_firs = [r.get("fir_number") for r in results if isinstance(r, dict) and r.get("fir_number")]
        log_entry = AuditLog(
            user_id=current_user.get("id"),
            username=current_user.get("username"),
            role=current_user.get("role"),
            method="GET",
            endpoint="/api/cases",
            status_code=200,
            query_text=f"filters: district={district}, crime={crime_type}, accused={accused_name}",
            returned_records={"total": total, "returned_count": len(results), "firs": returned_firs[:10]}
        )
        db.add(log_entry)
        db.commit()
    except Exception:
        db.rollback()
    
    return {
        "total": total,
        "results": results
    }

@router.get("/cases/{fir_id}")
def get_case(
    fir_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(ALLOWED_CASES_ROLES))
):
    case = get_case_by_id(fir_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    # Log audit entry
    try:
        log_entry = AuditLog(
            user_id=current_user.get("id"),
            username=current_user.get("username"),
            role=current_user.get("role"),
            method="GET",
            endpoint=f"/api/cases/{fir_id}",
            status_code=200,
            query_text=f"fir_id lookup: {fir_id}",
            returned_records={"fir_number": case.get("fir_number"), "crime_type": case.get("crime_type")}
        )
        db.add(log_entry)
        db.commit()
    except Exception:
        db.rollback()

    return case


