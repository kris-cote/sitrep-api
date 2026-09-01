from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AIProvenanceRecord(SQLModel, table=True):
    __tablename__ = "ai_provenance_records"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    mission_id: Optional[str] = Field(default=None, index=True)
    situation_id: Optional[str] = Field(default=None, index=True)
    decision_id: Optional[str] = Field(default=None, index=True)
    parent_run_id: Optional[str] = Field(default=None, index=True)
    role: str = Field(index=True)
    agent_version: str = "1.0"
    provider_id: Optional[str] = Field(default=None, index=True)
    model_name: Optional[str] = Field(default=None, index=True)
    data_classification: str = Field(default="public", index=True)
    sovereign_required: bool = False
    prompt_fingerprint: Optional[str] = Field(default=None, index=True)
    input_refs: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    request_payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    response_payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    evidence: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    assumptions: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    contradictions: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    information_gaps: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    confidence: float = 0.5
    advisory_only: bool = True
    status: str = Field(default="completed", index=True)
    error: Optional[str] = None
    operator_action: Optional[str] = Field(default=None, index=True)
    operator_actor: Optional[str] = None
    operator_note: Optional[str] = None
    operator_action_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
