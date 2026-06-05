# app/models/schemas.py
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    env: str


class TenantCreate(BaseModel):
    name: str
    plan_id: str = "starter"


class TenantRead(BaseModel):
    id: UUID
    name: str
    plan_id: str
    is_active: bool
    created_at: datetime


class MissionCreate(BaseModel):
    tenant_id: UUID
    name: str
    mission_type: str


class MissionRead(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    mission_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class EventCreate(BaseModel):
    tenant_id: Optional[UUID] = None
    mission_id: Optional[UUID] = None
    event_type: str
    source_system: str
    severity: str = "info"
    occurred_at: datetime
    payload: Dict[str, Any] = {}


class EventRead(EventCreate):
    id: UUID
    created_at: datetime


class CommandCreate(BaseModel):
    tenant_id: Optional[UUID] = None
    mission_id: Optional[UUID] = None
    target: str
    action: str
    params: Dict[str, Any] = {}


class CommandRead(CommandCreate):
    id: UUID
    status: str
    created_at: datetime


class AgentRunRequest(BaseModel):
    tenant_id: Optional[UUID] = None
    mission_id: Optional[UUID] = None
    input: Dict[str, Any]


class AgentRunResponse(BaseModel):
    agent: str
    status: str
    result: Dict[str, Any]

