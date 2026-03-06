from fastapi import APIRouter

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/status")
def get_status():
    """Mock endpoint for the hospital admin dashboard."""
    return {
        "active_hospitals": 1,
        "adapters_online": ["database", "api"],
        "sync_status": "healthy"
    }
