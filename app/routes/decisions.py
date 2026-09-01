from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.decision import CourseOfAction, DecisionAudit, DecisionRecord
from app.services.decision_engine import policy_flags, rank_courses_of_action, risk_label

router = APIRouter(prefix="/decisions", tags=["decision-intelligence"])


class CourseOfActionInput(BaseModel):
    name: str
    description: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_score: float = Field(default=0.5, ge=0.0, le=1.0)
    urgency_score: float = Field(default=0.5, ge=0.0, le=1.0)
    resource_score: float = Field(default=0.5, ge=0.0, le=1.0)
    reversibility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    policy_score: float = Field(default=1.0, ge=0.0, le=1.0)
    expected_outcomes: List[str] = []
    assumptions: List[str] = []
    constraints: List[str] = []
    rationale: List[str] = []
    metadata: Dict[str, Any] = {}


class DecisionGenerateRequest(BaseModel):
    situation_id: str
    mission_id: Optional[str] = None
    domain: str = "general"
    title: str
    summary: str = ""
    context: Dict[str, Any] = {}
    evidence: List[Dict[str, Any]] = []
    options: List[CourseOfActionInput]
    weights: Optional[Dict[str, float]] = None


class DecisionActionRequest(BaseModel):
    actor: str
    note: str = ""


def _serialize(decision: DecisionRecord, options: List[CourseOfAction]) -> Dict[str, Any]:
    return {
        "id": decision.id,
        "mission_id": decision.mission_id,
        "situation_id": decision.situation_id,
        "domain": decision.domain,
        "title": decision.title,
        "summary": decision.summary,
        "status": decision.status,
        "recommended_option_id": decision.recommended_option_id,
        "confidence": decision.confidence,
        "risk_level": decision.risk_level,
        "requires_human_authorization": decision.requires_human_authorization,
        "policy_flags": decision.policy_flags,
        "evidence": decision.evidence,
        "context": decision.context,
        "created_at": decision.created_at,
        "updated_at": decision.updated_at,
        "decided_at": decision.decided_at,
        "decided_by": decision.decided_by,
        "options": [
            {
                "id": option.id,
                "name": option.name,
                "description": option.description,
                "rank": option.rank,
                "score": option.score,
                "confidence": option.confidence,
                "risk_score": option.risk_score,
                "urgency_score": option.urgency_score,
                "resource_score": option.resource_score,
                "reversibility_score": option.reversibility_score,
                "policy_score": option.policy_score,
                "expected_outcomes": option.expected_outcomes,
                "assumptions": option.assumptions,
                "constraints": option.constraints,
                "rationale": option.rationale,
                "metadata": option.metadata_json,
            }
            for option in options
        ],
    }


@router.post("/generate", status_code=201)
def generate_decision(payload: DecisionGenerateRequest, session: Session = Depends(get_session)):
    if not payload.options:
        raise HTTPException(status_code=400, detail="At least one course of action is required")

    ranked = rank_courses_of_action([option.model_dump() for option in payload.options], payload.weights)
    flags = policy_flags(ranked)

    decision = DecisionRecord(
        mission_id=payload.mission_id,
        situation_id=payload.situation_id,
        domain=payload.domain,
        title=payload.title,
        summary=payload.summary,
        confidence=ranked[0].confidence,
        risk_level=risk_label(ranked),
        policy_flags=flags,
        evidence=payload.evidence,
        context=payload.context,
    )
    session.add(decision)
    session.flush()

    records: List[CourseOfAction] = []
    for index, item in enumerate(ranked, start=1):
        record = CourseOfAction(
            decision_id=decision.id,
            name=item.name,
            description=item.description,
            rank=index,
            score=item.score,
            confidence=item.confidence,
            risk_score=item.risk_score,
            urgency_score=item.urgency_score,
            resource_score=item.resource_score,
            reversibility_score=item.reversibility_score,
            policy_score=item.policy_score,
            expected_outcomes=item.expected_outcomes,
            assumptions=item.assumptions,
            constraints=item.constraints,
            rationale=item.rationale,
            metadata_json=item.metadata,
        )
        session.add(record)
        records.append(record)

    session.flush()
    decision.recommended_option_id = records[0].id
    session.add(DecisionAudit(
        decision_id=decision.id,
        action="generated",
        actor="decision-engine",
        payload={"recommended_option_id": records[0].id, "policy_flags": flags},
    ))
    session.commit()
    session.refresh(decision)
    return _serialize(decision, records)


@router.get("/{decision_id}")
def get_decision(decision_id: str, session: Session = Depends(get_session)):
    decision = session.get(DecisionRecord, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    options = session.exec(
        select(CourseOfAction)
        .where(CourseOfAction.decision_id == decision_id)
        .order_by(CourseOfAction.rank)
    ).all()
    return _serialize(decision, list(options))


@router.get("/{decision_id}/explanation")
def explain_decision(decision_id: str, session: Session = Depends(get_session)):
    decision = session.get(DecisionRecord, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    options = list(session.exec(
        select(CourseOfAction)
        .where(CourseOfAction.decision_id == decision_id)
        .order_by(CourseOfAction.rank)
    ).all())
    recommended = next((item for item in options if item.id == decision.recommended_option_id), None)
    return {
        "decision_id": decision.id,
        "status": decision.status,
        "recommended_option": recommended.name if recommended else None,
        "score": recommended.score if recommended else None,
        "rationale": recommended.rationale if recommended else [],
        "assumptions": recommended.assumptions if recommended else [],
        "constraints": recommended.constraints if recommended else [],
        "policy_flags": decision.policy_flags,
        "evidence": decision.evidence,
        "requires_human_authorization": decision.requires_human_authorization,
    }


def _change_status(decision_id: str, status: str, payload: DecisionActionRequest, session: Session):
    decision = session.get(DecisionRecord, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    if decision.status not in {"proposed", "approved", "rejected"}:
        raise HTTPException(status_code=409, detail=f"Decision cannot transition from {decision.status}")

    now = datetime.now(timezone.utc)
    decision.status = status
    decision.decided_at = now
    decision.decided_by = payload.actor
    decision.updated_at = now
    session.add(decision)
    session.add(DecisionAudit(
        decision_id=decision.id,
        action=status,
        actor=payload.actor,
        note=payload.note,
    ))
    session.commit()
    session.refresh(decision)
    return {"id": decision.id, "status": decision.status, "decided_by": decision.decided_by, "decided_at": decision.decided_at}


@router.post("/{decision_id}/approve")
def approve_decision(decision_id: str, payload: DecisionActionRequest, session: Session = Depends(get_session)):
    return _change_status(decision_id, "approved", payload, session)


@router.post("/{decision_id}/reject")
def reject_decision(decision_id: str, payload: DecisionActionRequest, session: Session = Depends(get_session)):
    return _change_status(decision_id, "rejected", payload, session)


@router.get("/{decision_id}/audit")
def get_decision_audit(decision_id: str, session: Session = Depends(get_session)):
    if not session.get(DecisionRecord, decision_id):
        raise HTTPException(status_code=404, detail="Decision not found")
    return list(session.exec(
        select(DecisionAudit)
        .where(DecisionAudit.decision_id == decision_id)
        .order_by(DecisionAudit.created_at)
    ).all())
