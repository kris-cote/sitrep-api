from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.models.db import get_session
from app.services.scenario_comparison import compare_scenarios

router = APIRouter(prefix="/scenario-comparison", tags=["scenario-comparison"])


class ScenarioBranch(BaseModel):
    branch_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    situation_changes: List[Dict[str, Any]] = []
    resource_changes: List[Dict[str, Any]] = []
    infrastructure_changes: List[Dict[str, Any]] = []
    reversibility_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    operational_continuity_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ScenarioComparisonRequest(BaseModel):
    tenant_id: str = "default"
    branches: List[ScenarioBranch]
    horizons_hours: Optional[List[float]] = None
    weights: Optional[Dict[str, float]] = None


@router.post("/rank")
def rank_scenario_branches(payload: ScenarioComparisonRequest, session: Session = Depends(get_session)):
    try:
        return compare_scenarios(
            session=session,
            tenant_id=payload.tenant_id,
            branches=[item.model_dump() for item in payload.branches],
            horizons_hours=payload.horizons_hours,
            weights=payload.weights,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
