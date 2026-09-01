from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.situation import SituationAudit, SituationRecord
from app.services.exposure_enrichment import enrich_situation_exposure
from app.services.wildfire_projection import wildfire_exposure_screen


router = APIRouter(prefix="/situations", tags=["situations"])


@router.get("")
def list_situations(
    tenant_id: str = Query(default="default"),
    status: str = Query(default="active"),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    statement = (
        select(SituationRecord)
        .where(SituationRecord.tenant_id == tenant_id)
        .where(SituationRecord.status == status)
        .order_by(SituationRecord.updated_at.desc())
        .limit(limit)
    )
    return list(session.exec(statement).all())


@router.get("/{situation_id}")
def get_situation(situation_id: str, session: Session = Depends(get_session)):
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise HTTPException(status_code=404, detail="Situation not found")
    return situation


@router.post("/{situation_id}/enrich/exposure")
def enrich_exposure(
    situation_id: str,
    radius_km: float | None = Query(default=None, gt=0, le=500),
    session: Session = Depends(get_session),
):
    try:
        return enrich_situation_exposure(session=session, situation_id=situation_id, radius_km=radius_km)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{situation_id}/enrich/wildfire-screen")
def wildfire_screen(
    situation_id: str,
    wind_from_deg: float = Query(ge=0, lt=360),
    wind_speed_kmh: float = Query(ge=0, le=250),
    horizon_hours: float = Query(default=6.0, gt=0, le=48),
    tenant_id: str = Query(default="default"),
    session: Session = Depends(get_session),
):
    try:
        return wildfire_exposure_screen(
            session=session,
            situation_id=situation_id,
            wind_from_deg=wind_from_deg,
            wind_speed_kmh=wind_speed_kmh,
            horizon_hours=horizon_hours,
            tenant_id=tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{situation_id}/audit")
def get_situation_audit(situation_id: str, session: Session = Depends(get_session)):
    if not session.get(SituationRecord, situation_id):
        raise HTTPException(status_code=404, detail="Situation not found")
    statement = (
        select(SituationAudit)
        .where(SituationAudit.situation_id == situation_id)
        .order_by(SituationAudit.created_at)
    )
    return list(session.exec(statement).all())
