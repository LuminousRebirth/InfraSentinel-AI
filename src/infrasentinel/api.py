from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from .config import get_settings
from .health import ReadinessResponse, readiness

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/live", response_model=LivenessResponse)
def live() -> LivenessResponse:
    settings = get_settings()
    return LivenessResponse(status="ok", service=settings.app_name, version=settings.app_version)


@router.get("/ready", response_model=ReadinessResponse)
def ready(response: Response) -> ReadinessResponse:
    result = readiness()
    if result.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
