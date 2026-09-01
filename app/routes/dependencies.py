from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.dependency import DependencyAudit, DependencyEdge
from app.services.dependency_graph import analyze_dependency_cascade

router = APIRouter(prefix="/dependencies", tags=["dependencies"])


class DependencyCreate(BaseModel):
    tenant_id: str = "default"
    upstream_type: str
    upstream_id: str
    downstream_type: str
    downstream_id: str
    relationship: str
    confidence: float = PydanticField(default=1.0, ge=0.0, le=1.0)
    criticality: float = PydanticField(default=0.5, ge=0.0, le=1.0)
    direction: str = "upstream_to_downstream"
    source_system: str = "manual"
    source_id: Optional[str] = None
    properties: Dict[str, Any] = {}


@router.post("", status_code=201)
def create_dependency(payload: DependencyCreate, session: Session = Depends(get_session)):
    edge = DependencyEdge(**payload.model_dump(), updated_at=datetime.now(timezone.utc))
    session.add(edge)
    session.flush()
    session.add(DependencyAudit(edge_id=edge.id, action="created", actor="api", payload=payload.model_dump()))
    session.commit()
    session.refresh(edge)
    return edge


@router.get("")
def list_dependencies(
    tenant_id: str = Query(default="default"),
    relationship: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    session: Session = Depends(get_session),
):
    statement = select(DependencyEdge).where(DependencyEdge.tenant_id == tenant_id)
    if relationship:
        statement = statement.where(DependencyEdge.relationship == relationship)
    statement = statement.order_by(DependencyEdge.updated_at.desc()).limit(limit)
    return list(session.exec(statement).all())


@router.get("/{edge_id}")
def get_dependency(edge_id: str, session: Session = Depends(get_session)):
    edge = session.get(DependencyEdge, edge_id)
    if not edge:
        raise HTTPException(status_code=404, detail="Dependency edge not found")
    return edge


@router.get("/cascade/analyze")
def analyze_cascade(
    seed_type: str = Query(...),
    seed_id: str = Query(...),
    tenant_id: str = Query(default="default"),
    max_depth: int = Query(default=4, ge=1, le=10),
    session: Session = Depends(get_session),
):
    return analyze_dependency_cascade(
        session=session,
        tenant_id=tenant_id,
        seed_type=seed_type,
        seed_id=seed_id,
        max_depth=max_depth,
    )
