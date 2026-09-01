from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.models.db import get_session
from app.services.ai_gateway import provider_catalog
from app.services.ai_intelligence import (
    analyze_situation,
    compare_ai_generated_branches,
    generate_coas,
    interpret_natural_language_plan,
    red_team_plan,
)

router = APIRouter(prefix="/ai", tags=["ai-intelligence"])


class AIRequestBase(BaseModel):
    data_classification: str = "public"
    preferred_provider: Optional[str] = None
    require_sovereign: bool = False


class SituationAIRequest(AIRequestBase):
    situation_id: str


class COARequest(AIRequestBase):
    situation_id: str
    objective: Optional[str] = None
    max_options: int = Field(default=5, ge=2, le=8)


class RedTeamRequest(AIRequestBase):
    situation_id: str
    candidate_plan: Dict[str, Any]


class NaturalLanguagePlanRequest(AIRequestBase):
    instruction: str = Field(min_length=3, max_length=12000)
    tenant_id: str = "default"
    compare_branches: bool = False
    weights: Optional[Dict[str, float]] = None


@router.get("/providers")
def list_ai_providers():
    return {
        "providers": provider_catalog(),
        "configuration_note": "Providers are configured by environment variables; secrets are never returned by this endpoint.",
        "supported_slots": ["openai", "canadian-ai", "local-ai"],
    }


@router.post("/situation-analyst")
async def situation_analyst(payload: SituationAIRequest, session: Session = Depends(get_session)):
    try:
        return await analyze_situation(
            session=session,
            situation_id=payload.situation_id,
            data_classification=payload.data_classification,
            preferred_provider=payload.preferred_provider,
            require_sovereign=payload.require_sovereign,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400 if "provider" in str(exc).lower() else 404, detail=str(exc)) from exc


@router.post("/coa-planner")
async def coa_planner(payload: COARequest, session: Session = Depends(get_session)):
    try:
        return await generate_coas(
            session=session,
            situation_id=payload.situation_id,
            objective=payload.objective,
            data_classification=payload.data_classification,
            preferred_provider=payload.preferred_provider,
            require_sovereign=payload.require_sovereign,
            max_options=payload.max_options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400 if "provider" in str(exc).lower() else 404, detail=str(exc)) from exc


@router.post("/red-team")
async def red_team(payload: RedTeamRequest, session: Session = Depends(get_session)):
    try:
        return await red_team_plan(
            session=session,
            situation_id=payload.situation_id,
            candidate_plan=payload.candidate_plan,
            data_classification=payload.data_classification,
            preferred_provider=payload.preferred_provider,
            require_sovereign=payload.require_sovereign,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400 if "provider" in str(exc).lower() else 404, detail=str(exc)) from exc


@router.post("/natural-language-plan")
async def natural_language_plan(payload: NaturalLanguagePlanRequest, session: Session = Depends(get_session)):
    try:
        parsed = await interpret_natural_language_plan(
            session=session,
            instruction=payload.instruction,
            tenant_id=payload.tenant_id,
            data_classification=payload.data_classification,
            preferred_provider=payload.preferred_provider,
            require_sovereign=payload.require_sovereign,
        )
        if not payload.compare_branches:
            return parsed
        comparison = await compare_ai_generated_branches(
            session=session,
            parsed_plan=parsed,
            tenant_id=payload.tenant_id,
            weights=payload.weights,
        )
        return {"parsed_plan": parsed, "comparison": comparison}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
