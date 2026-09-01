from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models.ai_provenance import AIProvenanceRecord
from app.models.db import get_session
from app.services.ai_gateway import provider_catalog
from app.services.ai_intelligence import (
    analyze_situation,
    compare_ai_generated_branches,
    generate_coas,
    interpret_natural_language_plan,
    red_team_plan,
)
from app.services.ai_orchestration import ask_sitrep, generate_briefing
from app.services.ai_provenance import set_operator_action

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


class AskRequest(AIRequestBase):
    question: str = Field(min_length=3, max_length=12000)
    tenant_id: str = "default"
    situation_id: Optional[str] = None
    candidate_plan: Optional[Dict[str, Any]] = None


class BriefingRequest(AIRequestBase):
    situation_id: str
    audience: str = Field(default="operator", min_length=2, max_length=80)


class OperatorAIAction(BaseModel):
    action: str = Field(min_length=2, max_length=80)
    actor: str = Field(min_length=2, max_length=200)
    note: str = Field(default="", max_length=4000)


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


@router.post("/ask")
async def ask(payload: AskRequest, session: Session = Depends(get_session)):
    try:
        return await ask_sitrep(
            session=session,
            question=payload.question,
            tenant_id=payload.tenant_id,
            situation_id=payload.situation_id,
            candidate_plan=payload.candidate_plan,
            data_classification=payload.data_classification,
            preferred_provider=payload.preferred_provider,
            require_sovereign=payload.require_sovereign,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/briefing")
async def briefing(payload: BriefingRequest, session: Session = Depends(get_session)):
    try:
        return await generate_briefing(
            session=session,
            situation_id=payload.situation_id,
            audience=payload.audience,
            data_classification=payload.data_classification,
            preferred_provider=payload.preferred_provider,
            require_sovereign=payload.require_sovereign,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400 if "provider" in str(exc).lower() else 404, detail=str(exc)) from exc


@router.get("/runs")
def list_ai_runs(
    tenant_id: str = Query(default="default"),
    situation_id: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    statement = select(AIProvenanceRecord).where(AIProvenanceRecord.tenant_id == tenant_id)
    if situation_id:
        statement = statement.where(AIProvenanceRecord.situation_id == situation_id)
    if role:
        statement = statement.where(AIProvenanceRecord.role == role)
    return list(session.exec(statement.order_by(AIProvenanceRecord.created_at.desc()).limit(limit)).all())


@router.get("/runs/{run_id}")
def get_ai_run(run_id: str, session: Session = Depends(get_session)):
    item = session.get(AIProvenanceRecord, run_id)
    if not item:
        raise HTTPException(status_code=404, detail="AI provenance record not found")
    return item


@router.post("/runs/{run_id}/operator-action")
def record_operator_action(run_id: str, payload: OperatorAIAction, session: Session = Depends(get_session)):
    try:
        return set_operator_action(session, run_id, payload.action, payload.actor, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
