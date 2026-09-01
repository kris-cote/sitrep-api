from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.resource_allocation import ResponseResourceAllocation
from app.services.resource_allocation import allocation_summary, create_allocation, update_allocation_status

router = APIRouter(prefix="/resource-allocations", tags=["resource-allocations"])


class AllocationCreate(BaseModel):
    tenant_id: str = "default"
    capability_id: str
    assignment_name: str
    requested_fraction: float = PydanticField(ge=0.0, le=1.0)
    allocated_fraction: float = PydanticField(ge=0.0, le=1.0)
    situation_id: Optional[str] = None
    decision_id: Optional[str] = None
    coa_id: Optional[str] = None
    priority: int = PydanticField(default=50, ge=0, le=100)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    constraints: Dict[str, Any] = {}
    metadata_json: Dict[str, Any] = {}
    created_by: str = "operator"
    allow_overcommit: bool = False


class AllocationStatusUpdate(BaseModel):
    status: str


@router.post("", status_code=201)
def allocate_resource(payload: AllocationCreate, session: Session = Depends(get_session)):
    try:
        return create_allocation(session=session, **payload.model_dump())
    except ValueError as exc:
        message = str(exc)
        status = 409 if "overcommit" in message.lower() else 400
        if "not found" in message.lower():
            status = 404
        raise HTTPException(status_code=status, detail=message) from exc


@router.get("")
def list_allocations(
    tenant_id: str = Query(default="default"),
    capability_id: Optional[str] = Query(default=None),
    situation_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    session: Session = Depends(get_session),
):
    statement = select(ResponseResourceAllocation).where(ResponseResourceAllocation.tenant_id == tenant_id)
    if capability_id:
        statement = statement.where(ResponseResourceAllocation.capability_id == capability_id)
    if situation_id:
        statement = statement.where(ResponseResourceAllocation.situation_id == situation_id)
    if status:
        statement = statement.where(ResponseResourceAllocation.status == status.lower().strip())
    return list(session.exec(statement.order_by(ResponseResourceAllocation.updated_at.desc()).limit(limit)).all())


@router.get("/capabilities/{capability_id}/summary")
def capability_allocation_summary(
    capability_id: str,
    starts_at: Optional[datetime] = Query(default=None),
    ends_at: Optional[datetime] = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        return allocation_summary(session=session, capability_id=capability_id, starts_at=starts_at, ends_at=ends_at)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{allocation_id}/status")
def set_allocation_status(allocation_id: str, payload: AllocationStatusUpdate, session: Session = Depends(get_session)):
    try:
        return update_allocation_status(session=session, allocation_id=allocation_id, status=payload.status)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(status_code=404 if "not found" in message.lower() else 400, detail=message) from exc
