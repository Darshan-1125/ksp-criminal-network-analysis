from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.db import SessionLocal
from app.models import FIRCase, Accused, Location, District, PoliceStation, CaseEmbedding
import json

def get_db_session():
    """Returns a new SQLAlchemy session instance."""
    return SessionLocal()

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
        "status": case.status,
        "mo_description": case.mo_description,
        "accused": [{"id": acc.id, "name": acc.name} for acc in case.accused],
        "victims": [{"vic": vic.id, "name": vic.name} for vic in case.victims],  # Note: contract has id/name or vic/name. Let's provide "id" and "name" to be safe and clean.
        "location": {
            "address": case.location.address if case.location else None,
            "lat": case.latitude,
            "lng": case.longitude
        }
    }
    # Standardize victim shape to match contract: [{"id": int, "name": str}]
    res["victims"] = [{"id": vic.id, "name": vic.name} for vic in case.victims]
    
    if include_narrative:
        res["narrative"] = case.narrative or ""
        
    return res

def search_cases_structured(filters: dict) -> list[dict]:
    """
    Search cases matching filters.
    filters can contain:
      - crime_type (str)
      - district (str)
      - date_from (str YYYY-MM-DD)
      - date_to (str YYYY-MM-DD)
      - accused_name (str)
      - limit (int)
      - offset (int)
    """
    db = SessionLocal()
    try:
        query = db.query(FIRCase)
        
        # Joins if filtering on relations
        if filters.get("district"):
            query = query.join(District, FIRCase.district_id == District.id).filter(
                District.name.ilike(f"%{filters['district']}%")
            )
            
        if filters.get("accused_name"):
            query = query.join(FIRCase.accused).filter(
                Accused.name.ilike(f"%{filters['accused_name']}%")
            )
            
        if filters.get("crime_type"):
            query = query.filter(FIRCase.crime_type.ilike(f"%{filters['crime_type']}%"))
            
        if filters.get("date_from"):
            query = query.filter(FIRCase.date_reported >= filters["date_from"])
            
        if filters.get("date_to"):
            query = query.filter(FIRCase.date_reported <= filters["date_to"])
            
        limit = filters.get("limit", 20)
        offset = filters.get("offset", 0)
        
        cases = query.offset(offset).limit(limit).all()
        return [serialize_case(c) for c in cases]
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

def get_network_for_entity(entity_type: str, entity_id: int) -> dict:
    """
    Returns the network graph for an entity (accused or location).
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
            
            # Fetch all cases for this accused
            cases = accused.cases
            for case in cases:
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
                            
            # Also find check for other accused who share phone or address directly (even if not in same case)
            if accused.phone or accused.address:
                shared_query = db.query(Accused).filter(Accused.id != accused.id)
                filters = []
                if accused.phone:
                    filters.append(Accused.phone == accused.phone)
                if accused.address:
                    filters.append(Accused.address == accused.address)
                shared_accused = shared_query.filter(or_(*filters)).all()
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
            
            # Fetch cases at this location
            cases = location.cases
            for case in cases:
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
