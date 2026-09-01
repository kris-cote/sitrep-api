from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.models.situation import SituationRecord
from app.services.ai_gateway import AIEvidenceContract, complete_json
from app.services.operational_forecast import forecast_operational_demand
from app.services.resource_optimizer import optimize_resource_plan
from app.services.scenario_comparison import compare_scenarios


BASE_POLICY = """
You are an advisory AI inside SitRep Decision Intelligence. The deterministic SitRep core is the source of truth for numeric scoring, geospatial calculations, resource availability, scenario ranking, and authorization. Never claim you executed an operational action. Never invent evidence, dependencies, sensor observations, resource availability, or authority. Distinguish observation from inference. Return JSON only. Include uncertainty and information gaps. Consequential actions always require human authorization.
""".strip()


def _situation_snapshot(session: Session, situation_id: str) -> Dict[str, Any]:
    item = session.get(SituationRecord, situation_id)
    if not item:
        raise ValueError("Situation not found")
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "mission_id": item.mission_id,
        "domain": item.domain,
        "status": item.status,
        "title": item.title,
        "summary": item.summary,
        "location": {"latitude": item.latitude, "longitude": item.longitude, "radius_km": item.radius_km},
        "confidence": item.confidence,
        "risk_score": item.risk_score,
        "urgency_score": item.urgency_score,
        "severity": item.severity,
        "source_types": item.source_types,
        "correlation_reasons": item.correlation_reasons,
        "evidence": item.evidence,
        "context": item.context,
        "observation_ids": item.observation_ids,
        "last_observed_at": item.last_observed_at,
    }


def _evidence_contract(raw: Dict[str, Any]) -> Dict[str, Any]:
    contract = AIEvidenceContract(
        summary=str(raw.get("summary") or ""),
        claims=list(raw.get("claims") or []),
        evidence=list(raw.get("evidence") or []),
        assumptions=[str(x) for x in raw.get("assumptions") or []],
        contradictions=[str(x) for x in raw.get("contradictions") or []],
        information_gaps=[str(x) for x in raw.get("information_gaps") or []],
        recommended_actions=list(raw.get("recommended_actions") or []),
        confidence=float(raw.get("confidence") or 0.5),
        model_provider=raw.get("model_provider"),
        model_name=raw.get("model_name"),
    )
    return contract.to_dict()


async def analyze_situation(
    session: Session,
    situation_id: str,
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
) -> Dict[str, Any]:
    situation = _situation_snapshot(session, situation_id)
    forecast = forecast_operational_demand(session, tenant_id=situation["tenant_id"], max_situations=100)
    optimizer = optimize_resource_plan(session, tenant_id=situation["tenant_id"], max_situations=100)
    result = await complete_json(
        system_prompt=BASE_POLICY + "\nRole: Situation Analyst. Explain what materially matters, what changed if evidence supports it, contradictions, and the most important information gaps. Claims must cite evidence IDs or source descriptions from the supplied SitRep data. Do not create COAs unless requested; recommended_actions should be information-gathering or operator-review actions when appropriate.",
        user_payload={"situation": situation, "operational_forecast": forecast, "resource_optimizer": optimizer},
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
    )
    return {"situation_id": situation_id, "analysis": _evidence_contract(result)}


async def generate_coas(
    session: Session,
    situation_id: str,
    objective: Optional[str] = None,
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
    max_options: int = 5,
) -> Dict[str, Any]:
    situation = _situation_snapshot(session, situation_id)
    optimizer = optimize_resource_plan(session, tenant_id=situation["tenant_id"], max_situations=100)
    forecast = forecast_operational_demand(session, tenant_id=situation["tenant_id"], max_situations=100)
    raw = await complete_json(
        system_prompt=BASE_POLICY + "\nRole: COA Planning Agent. Generate distinct candidate courses of action for operator review. Return {summary, assumptions, information_gaps, confidence, options:[...]}. Each option must include name, description, expected_outcomes, assumptions, constraints, rationale, confidence, risk_score, urgency_score, resource_score, reversibility_score, policy_score. Scores are preliminary AI estimates only and will be re-scored by SitRep. Do not include unlawful or unauthorized actions.",
        user_payload={"situation": situation, "objective": objective, "forecast": forecast, "resource_optimizer": optimizer, "max_options": max(2, min(8, max_options))},
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
    )
    options = list(raw.get("options") or [])[: max(2, min(8, max_options))]
    for option in options:
        option["ai_generated"] = True
        option["requires_deterministic_rescoring"] = True
        option["requires_human_authorization"] = True
    return {
        "situation_id": situation_id,
        "summary": raw.get("summary"),
        "assumptions": raw.get("assumptions") or [],
        "information_gaps": raw.get("information_gaps") or [],
        "confidence": raw.get("confidence", 0.5),
        "model_provider": raw.get("model_provider"),
        "model_name": raw.get("model_name"),
        "options": options,
        "policy": {"advisory_only": True, "deterministic_rescoring_required": True, "human_authorization_required": True},
    }


async def red_team_plan(
    session: Session,
    situation_id: str,
    candidate_plan: Dict[str, Any],
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
) -> Dict[str, Any]:
    situation = _situation_snapshot(session, situation_id)
    raw = await complete_json(
        system_prompt=BASE_POLICY + "\nRole: Red-Team Analyst. Challenge the candidate plan. Seek contradictory evidence, hidden assumptions, failure modes, second-order effects, missing information, and conditions under which another plan would be superior. Do not merely agree. Return the standard SitRep evidence contract JSON.",
        user_payload={"situation": situation, "candidate_plan": candidate_plan},
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
    )
    return {"situation_id": situation_id, "red_team": _evidence_contract(raw)}


async def interpret_natural_language_plan(
    session: Session,
    instruction: str,
    tenant_id: str = "default",
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
) -> Dict[str, Any]:
    situations = list(session.exec(
        select(SituationRecord).where(SituationRecord.tenant_id == tenant_id).where(SituationRecord.status == "active").limit(50)
    ).all())
    catalog = [{"id": s.id, "title": s.title, "domain": s.domain, "severity": s.severity, "risk_score": s.risk_score, "urgency_score": s.urgency_score} for s in situations]
    raw = await complete_json(
        system_prompt=BASE_POLICY + "\nRole: Natural-Language Planning Parser. Translate the operator request into structured SitRep scenario-comparison input. Return {intent, selected_situation_ids, branches:[{branch_id,name,description,situation_changes,resource_changes,infrastructure_changes,reversibility_score,operational_continuity_score,confidence}], horizons_hours, assumptions, information_gaps}. Do not invent database IDs. If the request references a resource or infrastructure feature for which no ID was provided in context, put it in information_gaps instead of fabricating an ID.",
        user_payload={"operator_instruction": instruction, "active_situations": catalog},
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
    )
    branches = list(raw.get("branches") or [])
    return {
        "instruction": instruction,
        "intent": raw.get("intent"),
        "selected_situation_ids": raw.get("selected_situation_ids") or [],
        "branches": branches,
        "horizons_hours": raw.get("horizons_hours") or [0.5, 2.0, 6.0, 24.0],
        "assumptions": raw.get("assumptions") or [],
        "information_gaps": raw.get("information_gaps") or [],
        "model_provider": raw.get("model_provider"),
        "model_name": raw.get("model_name"),
        "policy": {"translation_only": True, "simulation_not_executed": True, "human_review_required": True},
    }


async def compare_ai_generated_branches(
    session: Session,
    parsed_plan: Dict[str, Any],
    tenant_id: str = "default",
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    branches = parsed_plan.get("branches") or []
    if len(branches) < 2:
        raise ValueError("Natural-language planning request must produce at least two scenario branches before comparison")
    return compare_scenarios(
        session=session,
        tenant_id=tenant_id,
        branches=branches,
        horizons_hours=parsed_plan.get("horizons_hours"),
        weights=weights,
    )
