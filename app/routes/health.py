"""Health check routes."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/nextflow-api/health")
async def health():
    """Health check endpoint for service monitoring."""
    return {"status": "healthy"}
