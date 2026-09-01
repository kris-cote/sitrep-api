from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DependencyEdge(SQLModel, table=True):
    """Explicit dependency between SitRep assets/features.

    Edges are intentionally not inferred from proximity alone. They should come
    from an authoritative dataset, an authorized integration, or an operator.
    """

    __tablename__ = "dependency_edges"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    upstream_type: str = Field(index=True)   # exposure | infrastructure | entity | service
    upstream_id: str = Field(index=True)
    downstream_type: str = Field(index=True)
    downstream_id: str = Field(index=True)
    relationship: str = Field(index=True)   # supplies | access_route | carries | depends_on | backup_for
    confidence: float = 1.0
    criticality: float = 0.5
    direction: str = "upstream_to_downstream"
    source_system: str = "manual"
    source_id: Optional[str] = Field(default=None, index=True)
    properties: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class DependencyAudit(SQLModel, table=True):
    __tablename__ = "dependency_audit"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    edge_id: Optional[str] = Field(default=None, index=True)
    action: str = Field(index=True)
    actor: str = "system"
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
