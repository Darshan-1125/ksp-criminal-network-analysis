from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db import get_db_session
from app.models import FIRCase, District, Accused
from app.services.db_service import search_cases_structured, get_case_by_id

router = APIRouter(prefix="/api")

@router.get("/cases")
def get_cases(
    crime_type: Optional[str] = None,
    district: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    accused_name: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db_session)
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
    
    # Run query to get total
    query = db.query(FIRCase)
    if district:
        query = query.join(District, FIRCase.district_id == District.id).filter(
            District.name.ilike(f"%{district}%")
        )
    if accused_name:
        query = query.join(FIRCase.accused).filter(
            Accused.name.ilike(f"%{accused_name}%")
        )
    if crime_type:
        query = query.filter(FIRCase.crime_type.ilike(f"%{crime_type}%"))
    if date_from:
        query = query.filter(FIRCase.date_reported >= date_from)
    if date_to:
        query = query.filter(FIRCase.date_reported <= date_to)
        
    total = query.count()
    results = search_cases_structured(filters)
    
    return {
        "total": total,
        "results": results
    }

@router.get("/cases/{fir_id}")
def get_case(fir_id: str):
    case = get_case_by_id(fir_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case
