from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.db import SessionLocal
from app.models import FIRCase, Accused, Location, District, PoliceStation, CaseEmbedding
import json

def get_db_session():
    """Returns a new SQLAlchemy session instance."""
    return SessionLocal()

def format_status(status_str: str) -> str:
    """Standardizes status string into canonical Title Case for human-readable display."""
    if not status_str:
        return "Unknown"
    s = status_str.replace("_", " ").strip()
    if s.lower() == "under investigation":
        return "Under Investigation"
    elif s.lower() in ["charge sheeted", "chargesheeted"]:
        return "Charge Sheeted"
    return s.title()

def format_case_record(c: dict, index: Optional[int] = None) -> str:
    """
    Formats a case dictionary into a canonical, fixed-field Markdown string.
    If index is provided, prefixes with 'N. **FIR ...' for continuous list numbering.
    Fixed fields in exact order:
    - FIR Number
    - Crime Type
    - IPC Sections
    - District
    - Police Station
    - Date Reported
    - Status (Title Case)
    - MO Description
    - Accused
    - Victims
    """
    if not c:
        return ""
    fir_num = c.get("fir_number") or "N/A"
    crime_type = c.get("crime_type") or "N/A"
    ipc_sections = c.get("ipc_sections") or "N/A"
    district = c.get("district") or "N/A"
    police_station = c.get("police_station") or "N/A"
    date_reported = c.get("date_reported") or "N/A"
    status = format_status(c.get("status"))
    mo = c.get("mo_description") or "N/A"
    
    accused_list = c.get("accused", [])
    accused_str = ", ".join([a.get("name", "") for a in accused_list if isinstance(a, dict) and a.get("name")]) or "N/A"
    
    victim_list = c.get("victims", [])
    victim_str = ", ".join([v.get("name", "") for v in victim_list if isinstance(v, dict) and v.get("name")]) or "N/A"
    
    prefix = f"{index}." if index is not None else "-"
    return (
        f"{prefix} **FIR {fir_num}** | **Crime Type**: {crime_type} | **IPC**: {ipc_sections}\n"
        f"  - **District**: {district} | **Police Station**: {police_station}\n"
        f"  - **Date Reported**: {date_reported} | **Status**: {status}\n"
        f"  - **MO Description**: {mo}\n"
        f"  - **Accused**: {accused_str} | **Victims**: {victim_str}"
    )

def serialize_case(case: FIRCase, include_narrative: bool = False) -> dict:
    """Helper to convert a FIRCase SQLAlchemy object into the contract's JSON structure."""
    if not case:
        return {}
    
    res = {
        "id": case.id,
        "fir_number": case.fir_number,
        "crime_type": case.crime_type,
        "ipc_sections": case.ipc_sections,
        "district": case.district.name if case.district else None,
        "police_station": case.police_station.name if case.police_station else None,
        "date_reported": case.date_reported.strftime("%Y-%m-%d") if case.date_reported else None,
        "status": format_status(case.status),
        "mo_description": case.mo_description,
        "accused": [{"id": acc.id, "name": acc.name} for acc in case.accused],
        "victims": [{"id": vic.id, "name": vic.name} for vic in case.victims],
        "location": {
            "address": case.location.address if case.location else None,
            "lat": case.latitude,
            "lng": case.longitude
        }
    }
    
    if include_narrative:
        res["narrative"] = case.narrative or ""
        
    return res

DEFAULT_DETAIL_CAP = 15

def search_cases_structured(filters: dict) -> dict:
    """
    Search cases matching filters.
    filters can contain:
      - crime_type (str)
      - district (str)
      - status (str)
      - police_station (str)
      - ipc_section (str)
      - date_from (str YYYY-MM-DD)
      - date_to (str YYYY-MM-DD)
      - accused_name (str)
      - limit (int)
      - offset (int)
    Returns dict:
      {
        "total_count": int,
        "returned_count": int,
        "cases": list[dict]
      }
    """
    db = SessionLocal()
    try:
        query = db.query(FIRCase)
        
        # Joins if filtering on relations
        if filters.get("district"):
            query = query.join(District, FIRCase.district_id == District.id).filter(
                District.name.ilike(f"%{filters['district']}%")
            )

        if filters.get("police_station"):
            query = query.join(PoliceStation, FIRCase.police_station_id == PoliceStation.id).filter(
                PoliceStation.name.ilike(f"%{filters['police_station']}%")
            )
            
        if filters.get("accused_name"):
            query = query.join(FIRCase.accused).filter(
                Accused.name.ilike(f"%{filters['accused_name']}%")
            )
            
        if filters.get("crime_type"):
            query = query.filter(FIRCase.crime_type.ilike(f"%{filters['crime_type']}%"))

        if filters.get("status"):
            query = query.filter(FIRCase.status.ilike(f"%{filters['status']}%"))

        if filters.get("ipc_section"):
            query = query.filter(FIRCase.ipc_sections.ilike(f"%{filters['ipc_section']}%"))
            
        if filters.get("date_from"):
            query = query.filter(FIRCase.date_reported >= filters["date_from"])
            
        if filters.get("date_to"):
            query = query.filter(FIRCase.date_reported <= filters["date_to"])

        total_count = query.count()
        limit = filters.get("limit", DEFAULT_DETAIL_CAP)
        offset = filters.get("offset", 0)
        
        cases = query.order_by(FIRCase.date_reported.desc()).offset(offset).limit(limit).all()
        serialized_cases = [serialize_case(c) for c in cases]
        return {
            "total_count": total_count,
            "returned_count": len(serialized_cases),
            "cases": serialized_cases
        }
    finally:
        db.close()

def get_case_by_id(fir_id: str) -> dict:
    """
    Get a single case including narrative, searching by case ID or FIR number.
    """
    db = SessionLocal()
    try:
        case = None
        # Try as integer ID first
        if fir_id.isdigit():
            case = db.query(FIRCase).filter(FIRCase.id == int(fir_id)).first()
            
        if not case:
            # Fallback/default search by FIR number
            case = db.query(FIRCase).filter(FIRCase.fir_number == fir_id).first()
            
        return serialize_case(case, include_narrative=True) if case else {}
    finally:
        db.close()

def get_network_for_entity(entity_type: str, entity_id: int, cases: Optional[List[Any]] = None) -> dict:
    """
    Returns the network graph for an entity (accused or location).
    If `cases` is provided, scopes the network nodes and edges strictly to those cases.
    Nodes shape: [{"id": str, "label": str, "type": "accused"|"case"|"location"}]
    Edges shape: [{"source": str, "target": str, "relation": str}]
    """
    db = SessionLocal()
    nodes = {}
    edges = []
    
    def add_node(node_id, label, type_name):
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label, "type": type_name}
            
    def add_edge(source, target, relation):
        # Prevent duplicates
        for edge in edges:
            if edge["source"] == source and edge["target"] == target and edge["relation"] == relation:
                return
        edges.append({"source": source, "target": target, "relation": relation})

    try:
        if entity_type == "accused":
            # Start with the accused
            accused = db.query(Accused).filter(Accused.id == entity_id).first()
            if not accused:
                return {"nodes": [], "edges": []}
                
            accused_node_id = f"accused_{accused.id}"
            add_node(accused_node_id, accused.name, "accused")
            
            # Fetch cases for this accused (or use scoped cases if provided)
            target_cases = cases if cases is not None else accused.cases
            for c in target_cases:
                # Resolve case object from DB session if needed
                case_id = c.id if hasattr(c, "id") else (c.get("id") if isinstance(c, dict) else None)
                if not case_id:
                    continue
                case = db.query(FIRCase).filter(FIRCase.id == case_id).first()
                if not case:
                    continue

                case_node_id = f"case_{case.id}"
                add_node(case_node_id, case.fir_number, "case")
                add_edge(accused_node_id, case_node_id, "accused_in")
                
                # Add location
                if case.location:
                    loc = case.location
                    loc_label = f"{loc.address or ''}, {loc.city or ''}".strip(", ")
                    if not loc_label:
                        loc_label = f"Location {loc.id}"
                    loc_node_id = f"location_{loc.id}"
                    add_node(loc_node_id, loc_label, "location")
                    add_edge(case_node_id, loc_node_id, "occurred_at")
                    
                # Add other accused in the same case
                for other_acc in case.accused:
                    if other_acc.id != accused.id:
                        other_acc_node_id = f"accused_{other_acc.id}"
                        add_node(other_acc_node_id, other_acc.name, "accused")
                        add_edge(other_acc_node_id, case_node_id, "accused_in")
                        
                        # Check shared contact (phone or address)
                        if (accused.phone and other_acc.phone and accused.phone == other_acc.phone) or \
                           (accused.address and other_acc.address and accused.address == other_acc.address):
                            add_edge(accused_node_id, other_acc_node_id, "shared_contact")
                            
            # Check for direct shared contacts only when unfiltered
            if cases is None and (accused.phone or accused.address):
                shared_query = db.query(Accused).filter(Accused.id != accused.id)
                filters_list = []
                if accused.phone:
                    filters_list.append(Accused.phone == accused.phone)
                if accused.address:
                    filters_list.append(Accused.address == accused.address)
                shared_accused = shared_query.filter(or_(*filters_list)).all()
                for sa in shared_accused:
                    sa_node_id = f"accused_{sa.id}"
                    add_node(sa_node_id, sa.name, "accused")
                    add_edge(accused_node_id, sa_node_id, "shared_contact")

        elif entity_type == "location":
            location = db.query(Location).filter(Location.id == entity_id).first()
            if not location:
                return {"nodes": [], "edges": []}
                
            loc_label = f"{location.address or ''}, {location.city or ''}".strip(", ")
            if not loc_label:
                loc_label = f"Location {location.id}"
            loc_node_id = f"location_{location.id}"
            add_node(loc_node_id, loc_label, "location")
            
            target_cases = cases if cases is not None else location.cases
            for c in target_cases:
                case_id = c.id if hasattr(c, "id") else (c.get("id") if isinstance(c, dict) else None)
                if not case_id:
                    continue
                case = db.query(FIRCase).filter(FIRCase.id == case_id).first()
                if not case:
                    continue

                case_node_id = f"case_{case.id}"
                add_node(case_node_id, case.fir_number, "case")
                add_edge(case_node_id, loc_node_id, "occurred_at")
                
                # Add accused involved in these cases
                for acc in case.accused:
                    acc_node_id = f"accused_{acc.id}"
                    add_node(acc_node_id, acc.name, "accused")
                    add_edge(acc_node_id, case_node_id, "accused_in")
                    
        return {
            "nodes": list(nodes.values()),
            "edges": edges
        }
    finally:
        db.close()
