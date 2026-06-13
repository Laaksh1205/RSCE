import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.analysis import router as analysis_router
from api.routes.results import router as results_router
from src.storage import init_db
from src.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Research Synthesis & Contradiction Engine (RSCE) REST API",
    description="Backend REST API providing paper ingestion, claim extraction, contradiction detection, and claim graph synthesis.",
    version="1.0.0"
)

# Bind CORS middleware to restrict allowed origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    logger.info("Initializing database...")
    init_db()

@app.get("/api/health")
async def health_check():
    """Simple API health check endpoint."""
    return {"status": "healthy", "service": "rsce-api"}

# Mount routing modules
app.include_router(analysis_router)
app.include_router(results_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=True)
