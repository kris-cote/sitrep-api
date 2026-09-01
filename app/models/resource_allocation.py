from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResponseResourceAllocation(SQLModel, table=True):
    __tablename__ = "response_resource_allocations"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    capability_id: str = Field(index=True)
    situation_id: Optional[str] = Field(default=None, index=True)
    decision_id: Optional[str] = Field(default=None, index=True)
    coa_id: Optional[str] = Field(default=None, index=True)
    assignment_name: str = Field(index=True)
    status: str = Field(default="planned", index=True)
    requested_fraction: float = 0.0
    allocated_fraction: float = 0.0
    priority: int = Field(default=50, index=True)
    starts_at: Optional[datetime] = Field(default=None, index=True)
    ends_at: Optional[datetime] = Field(default=None, index=True)
    constraints: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    metadata_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_by: str = "operator"
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
