from fastapi import FastAPI
from app.core.config import settings
from app.api.endpoints import router as api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Asynchronous processing pipeline for cleaning financial transaction data, detecting anomalies, and generating AI insights.",
    version="1.0.0"
)

# Root/Health check endpoint
@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": "1.0.0"
    }

# Include API Router
app.include_router(api_router)
