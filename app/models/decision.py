from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DecisionRecord(SQLModel, table=True):
    __tablename__ = "decision_records"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    mission_id: Optional[str] = Field(default=None, index=True)
    situation_id: str = Field(index=True)
    domain: str = Field(default="general", index=True)
    title: str
    summary: str = ""
    status: str = Field(default="proposed", index=True)
    recommended_option_id: Optional[str] = None
    confidence: float = 0.0
    risk_level: str = "unknown"
    requires_human_authorization: bool = True
    policy_flags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    evidence: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    context: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None


class CourseOfAction(SQLModel, table=True):
    __tablename__ = "courses_of_action"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    decision_id: str = Field(index=True)
    name: str
    description: str = ""
    rank: int = 0
    score: float = 0.0
    confidence: float = 0.0
    risk_score: float = 0.0
    urgency_score: float = 0.0
    resource_score: float = 0.0
    reversibility_score: float = 0.0
    policy_score: float = 1.0
    expected_outcomes: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    assumptions: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    constraints: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    rationale: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    metadata_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class DecisionAudit(SQLModel, table=True):
    __tablename__ = "decision_audit"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    decision_id: str = Field(index=True)
    action: str = Field(index=True)
    actor: str = "system"
    note: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
