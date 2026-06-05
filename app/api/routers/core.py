# app/api/routers/core.py
from fastapi import APIRouter
from app.core.config import settings
from app.models.schemas import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["core"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="Space Hub - The Veil",
        env=settings.env,
    )


@router.get("/healthz")
def healthz():
    return {"ok": True}
