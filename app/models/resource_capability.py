from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResponseResourceCapability(SQLModel, table=True):
    __tablename__ = "response_resource_capabilities"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    exposure_asset_id: str = Field(index=True)
    resource_type: str = Field(index=True)
    name: str = Field(index=True)
    availability_status: str = Field(default="unknown", index=True)
    availability_score: float = 0.5
    readiness_score: float = 0.5
    capacity_score: float = 0.5
    suitability_score: float = 0.5
    capabilities: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    capacity: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    suitability: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    constraints: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    source_system: str = "manual"
    source_id: Optional[str] = Field(default=None, index=True)
    properties: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
