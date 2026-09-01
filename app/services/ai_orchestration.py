from __future__ import annotations

from typing import Any, Dict, Optional

from sqlmodel import Session

from app.services.ai_gateway import complete_json
from app.services.ai_intelligence import analyze_situation, generate_coas, interpret_natural_language_plan, red_team_plan
from app.services.ai_provenance import record_ai_run
from app.services.operational_forecast import forecast_operational_demand
from app.services.resource_optimizer import optimize_resource_plan


ORCHESTRATOR_POLICY = """
You are SitRep's AI orchestration layer. You are advisory only. Never claim an operational action was executed. Deterministic SitRep services are authoritative for calculations, resource status, scenario ranking and authorization. Return JSON only. Distinguish known facts from inference and identify uncertainty.
""".strip()


def classify_intent(question: str) -> str:
    text = (question or "").lower()
    if any(x in text for x in ("what if", "assume", "scenario", "compare plan", "compare option")):
        return "scenario"
    if any(x in text for x in ("course of action", "coa", "what should we do", "options", "plan options")):
        return "coa"
    if any(x in text for x in ("challenge", "red team", "why is this wrong", "failure mode")):
        return "red-team"
    if any(x in text for x in ("forecast", "next hour", "next 6", "tomorrow", "future demand", "pre-stage")):
        return "forecast"
    if any(x in text for x in ("resources", "allocation", "where should", "capacity", "available capability")):
        return "resources"
    if any(x in text for x in ("brief", "briefing", "sitrep summary", "executive summary", "commander")):
        return "briefing"
    return "situation"


async def generate_briefing(
    session: Session,
    *,
    situation_id: str,
    audience: str = "operator",
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
) -> Dict[str, Any]:
    analysis = await analyze_situation(
        session=session,
        situation_id=situation_id,
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
    )
    raw = await complete_json(
        system_prompt=ORCHESTRATOR_POLICY + "\nRole: Briefing Agent. Produce a concise operational briefing from supplied SitRep analysis. Return {headline, situation, key_changes, risks, resource_state, decisions_required, information_gaps, confidence}. Do not introduce facts absent from the supplied analysis.",
        user_payload={"audience": audience, "analysis": analysis},
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
    )
    return {"situation_id": situation_id, "audience": audience, "briefing": raw}


async def ask_sitrep(
    session: Session,
    *,
    question: str,
    tenant_id: str = "default",
    situation_id: Optional[str] = None,
    candidate_plan: Optional[Dict[str, Any]] = None,
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
) -> Dict[str, Any]:
    intent = classify_intent(question)
    request_payload = {
        "question": question,
        "tenant_id": tenant_id,
        "situation_id": situation_id,
        "candidate_plan": candidate_plan,
        "intent": intent,
    }

    if intent in {"situation", "coa", "red-team", "briefing"} and not situation_id:
        raise ValueError(f"situation_id is required for intent={intent}")

    if intent == "situation":
        result = await analyze_situation(session, situation_id, data_classification, preferred_provider, require_sovereign)
    elif intent == "coa":
        result = await generate_coas(session, situation_id, question, data_classification, preferred_provider, require_sovereign)
    elif intent == "red-team":
        if not candidate_plan:
            raise ValueError("candidate_plan is required for red-team requests")
        result = await red_team_plan(session, situation_id, candidate_plan, data_classification, preferred_provider, require_sovereign)
    elif intent == "scenario":
        result = await interpret_natural_language_plan(session, question, tenant_id, data_classification, preferred_provider, require_sovereign)
    elif intent == "forecast":
        result = forecast_operational_demand(session, tenant_id=tenant_id)
    elif intent == "resources":
        result = optimize_resource_plan(session, tenant_id=tenant_id)
    elif intent == "briefing":
        result = await generate_briefing(
            session,
            situation_id=situation_id,
            audience="operator",
            data_classification=data_classification,
            preferred_provider=preferred_provider,
            require_sovereign=require_sovereign,
        )
    else:
        raise ValueError(f"Unsupported orchestrator intent: {intent}")

    run = record_ai_run(
        session,
        role=f"orchestrator:{intent}",
        request_payload=request_payload,
        response_payload=result if isinstance(result, dict) else {"result": result},
        tenant_id=tenant_id,
        situation_id=situation_id,
        data_classification=data_classification,
        sovereign_required=require_sovereign,
        input_refs=[{"type": "situation", "id": situation_id}] if situation_id else [],
    )
    return {
        "intent": intent,
        "answer": result,
        "ai_run_id": run.id,
        "policy": {
            "advisory_only": True,
            "deterministic_core_is_source_of_truth": True,
            "human_authorization_required_for_consequential_actions": True,
        },
    }
