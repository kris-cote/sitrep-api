from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SituationRecord(SQLModel, table=True):
    __tablename__ = "situations"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    mission_id: Optional[str] = Field(default=None, index=True)
    domain: str = Field(default="general", index=True)
    status: str = Field(default="active", index=True)
    title: str
    summary: str = ""
    latitude: Optional[float] = Field(default=None, index=True)
    longitude: Optional[float] = Field(default=None, index=True)
    radius_km: float = 25.0
    confidence: float = 0.0
    risk_score: float = 0.0
    urgency_score: float = 0.0
    severity: str = Field(default="low", index=True)
    source_types: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    observation_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    correlation_reasons: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    evidence: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    context: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)
    last_observed_at: datetime = Field(default_factory=utcnow, index=True)


class SituationAudit(SQLModel, table=True):
    __tablename__ = "situation_audit"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    situation_id: str = Field(index=True)
    action: str = Field(index=True)
    observation_id: Optional[str] = Field(default=None, index=True)
    note: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
