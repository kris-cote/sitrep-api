# app/api/routers/core.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.core.database_health import database_ready
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

@router.get("/readyz")
def readyz():
    connected = database_ready()
    return JSONResponse(
        status_code=200 if connected else 503,
        content={
            "ok": connected,
            "status": "ready" if connected else "unavailable",
            "database": "connected" if connected else "unavailable",
        },
        headers={"Cache-Control": "no-store"},
    )
