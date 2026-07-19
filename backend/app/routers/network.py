from fastapi import APIRouter, HTTPException
from app.services.db_service import get_network_for_entity

router = APIRouter(prefix="/api")

@router.get("/network/{entity_type}/{entity_id}")
def get_network(entity_type: str, entity_id: int):
    if entity_type not in ["accused", "location"]:
        raise HTTPException(status_code=400, detail="Invalid entity_type. Must be 'accused' or 'location'.")
        
    network_data = get_network_for_entity(entity_type, entity_id)
    if not network_data or not network_data.get("nodes"):
        raise HTTPException(status_code=404, detail="Entity or network not found.")
        
    return network_data
