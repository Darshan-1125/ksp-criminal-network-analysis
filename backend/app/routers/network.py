from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db_session
from app.models import AuditLog
from app.services.db_service import get_network_for_entity
from app.services.auth_service import require_role

router = APIRouter(prefix="/api")

ALLOWED_NETWORK_ROLES = ["admin", "supervisor", "investigator", "analyst"]

@router.get("/network/{entity_type}/{entity_id}")
def get_network(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(ALLOWED_NETWORK_ROLES))
):
    if entity_type not in ["accused", "location"]:
        raise HTTPException(status_code=400, detail="Invalid entity_type. Must be 'accused' or 'location'.")
        
    network_data = get_network_for_entity(entity_type, entity_id)
    if not network_data or not network_data.get("nodes"):
        raise HTTPException(status_code=404, detail="Entity or network not found.")

    # Audit Log Recording
    try:
        nodes_count = len(network_data.get("nodes", []))
        edges_count = len(network_data.get("edges", []))
        log_entry = AuditLog(
            user_id=current_user.get("id"),
            username=current_user.get("username"),
            role=current_user.get("role"),
            method="GET",
            endpoint=f"/api/network/{entity_type}/{entity_id}",
            status_code=200,
            query_text=f"network query: entity_type={entity_type}, entity_id={entity_id}",
            returned_records={"nodes_count": nodes_count, "edges_count": edges_count}
        )
        db.add(log_entry)
        db.commit()
    except Exception:
        db.rollback()
        
    return network_data


