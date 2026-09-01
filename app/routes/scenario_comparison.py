from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.models.db import get_session
from app.services.scenario_comparison import compare_scenarios
from app.services.scenario_decision import promote_scenario_comparison

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


class ScenarioPromotionRequest(ScenarioComparisonRequest):
    situation_id: str
    selected_branch_id: Optional[str] = None
    mission_id: Optional[str] = None
    domain: str = "general"
    title: str = "Scenario planning decision"
    summary: str = ""
    actor: str = "operator"


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


@router.post("/promote", status_code=201)
def promote_scenario_branch(payload: ScenarioPromotionRequest, session: Session = Depends(get_session)):
    try:
        return promote_scenario_comparison(
            session=session,
            tenant_id=payload.tenant_id,
            situation_id=payload.situation_id,
            selected_branch_id=payload.selected_branch_id,
            mission_id=payload.mission_id,
            domain=payload.domain,
            title=payload.title,
            summary=payload.summary,
            actor=payload.actor,
            branches=[item.model_dump() for item in payload.branches],
            horizons_hours=payload.horizons_hours,
            weights=payload.weights,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
