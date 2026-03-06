from fastapi import FastAPI
from shared.db.connection import engine, Base
from middleware.app.models import domain
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize DB tables for the middleware
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="HMS Middleware API",
    description="Dynamic Adapters and Onboarding API for existing HMS integrations",
    version="1.0.0"
)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "middleware"}

from middleware.app.routes import onboarding_router, dashboard_router

app.include_router(onboarding_router)
app.include_router(dashboard_router)
