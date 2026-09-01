from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.models.db import get_session
from app.services.canada_emergency_import import (
    CanadaEmergencyImportError,
    emergency_coverage,
    import_on_affes,
    import_qc_fire_stations,
)

router = APIRouter(prefix="/api/v1/connectors/canada/emergency", tags=["canadian-emergency-infrastructure"])


@router.get("/coverage")
def coverage():
    return emergency_coverage()


@router.post("/on/import")
async def import_ontario_emergency(
    bbox: str | None = Query(default=None, description="Optional minLon,minLat,maxLon,maxLat"),
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    limit: int = Query(default=2000, ge=1, le=2000),
    session: Session = Depends(get_session),
):
    try:
        return await import_on_affes(session=session, tenant_id=tenant_id, bbox=bbox, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CanadaEmergencyImportError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "Ontario AFFES", "error": str(exc)}) from exc


@router.post("/qc/fire-stations/import")
async def import_quebec_fire_stations(
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    limit: int = Query(default=5000, ge=1, le=5000),
    session: Session = Depends(get_session),
):
    try:
        return await import_qc_fire_stations(session=session, tenant_id=tenant_id, limit=limit)
    except CanadaEmergencyImportError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "Quebec public fire stations", "error": str(exc)}) from exc
