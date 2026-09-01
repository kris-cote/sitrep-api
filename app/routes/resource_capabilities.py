from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.exposure import ExposureAsset
from app.models.resource_capability import ResponseResourceCapability

router = APIRouter(prefix="/resource-capabilities", tags=["resource-capabilities"])

ALLOWED_AVAILABILITY = {"available", "limited", "unavailable", "unknown", "maintenance", "committed"}


class ResourceCapabilityCreate(BaseModel):
    tenant_id: str = "default"
    exposure_asset_id: str
    resource_type: str
    name: str
    availability_status: str = "unknown"
    availability_score: float = PydanticField(default=0.5, ge=0.0, le=1.0)
    readiness_score: float = PydanticField(default=0.5, ge=0.0, le=1.0)
    capacity_score: float = PydanticField(default=0.5, ge=0.0, le=1.0)
    suitability_score: float = PydanticField(default=0.5, ge=0.0, le=1.0)
    capabilities: List[str] = []
    capacity: Dict[str, Any] = {}
    suitability: Dict[str, Any] = {}
    constraints: List[str] = []
    source_system: str = "manual"
    source_id: Optional[str] = None
    properties: Dict[str, Any] = {}
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class AvailabilityUpdate(BaseModel):
    availability_status: str
    availability_score: float = PydanticField(ge=0.0, le=1.0)
    readiness_score: Optional[float] = PydanticField(default=None, ge=0.0, le=1.0)
    capacity_score: Optional[float] = PydanticField(default=None, ge=0.0, le=1.0)
    suitability_score: Optional[float] = PydanticField(default=None, ge=0.0, le=1.0)
    constraints: Optional[List[str]] = None
    properties: Optional[Dict[str, Any]] = None


def _validate_status(status: str) -> str:
    normalized = status.lower().strip()
    if normalized not in ALLOWED_AVAILABILITY:
        raise HTTPException(status_code=400, detail=f"Unsupported availability_status: {status}")
    return normalized


@router.post("", status_code=201)
def create_resource_capability(payload: ResourceCapabilityCreate, session: Session = Depends(get_session)):
    asset = session.get(ExposureAsset, payload.exposure_asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Exposure asset not found")
    if asset.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=400, detail="Resource capability tenant must match exposure asset tenant")
    data = payload.model_dump()
    data["availability_status"] = _validate_status(payload.availability_status)
    record = ResponseResourceCapability(**data)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.get("")
def list_resource_capabilities(
    tenant_id: str = Query(default="default"),
    exposure_asset_id: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    availability_status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    session: Session = Depends(get_session),
):
    statement = select(ResponseResourceCapability).where(ResponseResourceCapability.tenant_id == tenant_id)
    if exposure_asset_id:
        statement = statement.where(ResponseResourceCapability.exposure_asset_id == exposure_asset_id)
    if resource_type:
        statement = statement.where(ResponseResourceCapability.resource_type == resource_type)
    if availability_status:
        statement = statement.where(ResponseResourceCapability.availability_status == _validate_status(availability_status))
    return list(session.exec(statement.order_by(ResponseResourceCapability.updated_at.desc()).limit(limit)).all())


@router.get("/{capability_id}")
def get_resource_capability(capability_id: str, session: Session = Depends(get_session)):
    item = session.get(ResponseResourceCapability, capability_id)
    if not item:
        raise HTTPException(status_code=404, detail="Resource capability not found")
    return item


@router.patch("/{capability_id}/availability")
def update_resource_availability(capability_id: str, payload: AvailabilityUpdate, session: Session = Depends(get_session)):
    item = session.get(ResponseResourceCapability, capability_id)
    if not item:
        raise HTTPException(status_code=404, detail="Resource capability not found")
    item.availability_status = _validate_status(payload.availability_status)
    item.availability_score = payload.availability_score
    if payload.readiness_score is not None:
        item.readiness_score = payload.readiness_score
    if payload.capacity_score is not None:
        item.capacity_score = payload.capacity_score
    if payload.suitability_score is not None:
        item.suitability_score = payload.suitability_score
    if payload.constraints is not None:
        item.constraints = payload.constraints
    if payload.properties is not None:
        merged = dict(item.properties or {})
        merged.update(payload.properties)
        item.properties = merged
    item.updated_at = datetime.now(timezone.utc)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
