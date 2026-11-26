"""Health-check API endpoints."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.schemas.health import HealthResponse
from app.services.health_service import get_system_health

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Verify API and database health",
    responses={
        200: {"description": "API and database are healthy."},
        503: {"description": "API is running, but database connectivity failed."},
    },
)
def health_check() -> JSONResponse:
    """Return service and database connectivity status without exposing secrets."""
    payload = get_system_health()
    http_status = (
        status.HTTP_200_OK
        if payload.status == "ok"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=http_status, content=payload.model_dump(mode="json"))
