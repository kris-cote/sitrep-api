# app/api/routers/missions.py
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from uuid import UUID
from datetime import datetime

from app.models.db import get_session
from app.models.entities import Mission, Tenant
from app.models.schemas import MissionCreate, MissionRead
from app.core.security import verify_api_key

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])


@router.post("", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
def create_mission(
    payload: MissionCreate,
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    tenant = session.get(Tenant, payload.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    mission = Mission(
        tenant_id=payload.tenant_id,
        name=payload.name,
        mission_type=payload.mission_type,
    )
    session.add(mission)
    session.commit()
    session.refresh(mission)
    return mission


@router.get("", response_model=List[MissionRead])
def list_missions(
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    missions = session.exec(select(Mission)).all()
    return missions


@router.get("/{mission_id}", response_model=MissionRead)
def get_mission(
    mission_id: UUID,
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    mission = session.get(Mission, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.post("/{mission_id}/abort", response_model=MissionRead)
def abort_mission(
    mission_id: UUID,
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    mission = session.get(Mission, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission.status = "aborted"
    mission.updated_at = datetime.utcnow()
    session.add(mission)
    session.commit()
    session.refresh(mission)
    return mission
