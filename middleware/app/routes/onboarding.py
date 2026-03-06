from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from shared.db.connection import get_db
from middleware.app.models.domain import Hospital, IntegrationConfig, FieldMapping
from middleware.app.adapters.engine import AdapterEngine
from middleware.app.services.mapping_service import MappingService

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])
mapping_svc = MappingService()

class ConnectionTestRequest(BaseModel):
    source_type: str
    connection_details: Dict[str, Any]

@router.post("/test-connection")
def test_connection(req: ConnectionTestRequest):
    """Test connection to the external HMS system before saving."""
    try:
        adapter = AdapterEngine.get_adapter(req.source_type, req.connection_details)
        if adapter.test_connection():
            return {"status": "success", "message": "Connection successful"}
        else:
            raise HTTPException(status_code=400, detail="Connection failed. Please check credentials.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
@router.post("/suggest-mapping")
def suggest_mapping(fields: List[str]):
    """Automatically suggest mappings from external HMS fields to standard schema."""
    return mapping_svc.suggest_mappings(fields)

@router.post("/hospitals")
def create_hospital(name: str, db: Session = Depends(get_db)):
    """Create a new hospital tenant."""
    h = Hospital(name=name)
    db.add(h)
    db.commit()
    db.refresh(h)
    return {"id": h.id, "name": h.name}
