from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlmodel import Session

from app.services.ai_gateway import complete_json
from app.services.ai_intelligence import analyze_situation, generate_coas, interpret_natural_language_plan, red_team_plan
from app.services.ai_provenance import record_ai_run
from app.services.ai_tool_registry import execute_tool, tool_catalog
from app.services.operational_forecast import forecast_operational_demand
from app.services.resource_optimizer import optimize_resource_plan


ORCHESTRATOR_POLICY = """
You are SitRep's AI orchestration layer. You are advisory only. Never claim an operational action was executed. Deterministic SitRep services are authoritative for calculations, resource status, scenario ranking and authorization. Return JSON only. Distinguish known facts from inference and identify uncertainty. Never invent database IDs, evidence, dependencies, resource availability or tool results.
""".strip()


TOOL_PLANNER_POLICY = ORCHESTRATOR_POLICY + """
\nRole: Tool Planner. Select the minimum SitRep deterministic tools needed to answer the operator question. Return {tool_calls:[{tool_name,arguments,reason}],reasoning_summary}. Use only names from tool_catalog. Prefer read-only tools. Do not select a mutating tool unless the question clearly requires recalculating/updating that enrichment; mutating tools may still be blocked by policy. Maximum 5 tool calls. If existing context is sufficient, return an empty tool_calls list.
"""


TOOL_SYNTHESIS_POLICY = ORCHESTRATOR_POLICY + """
\nRole: Situation Analyst with tool results. Answer using only the supplied operator question, scope and completed SitRep tool results. Return {summary,claims,evidence,assumptions,contradictions,information_gaps,recommended_actions,confidence}. Each material claim should point to a tool_name and a specific result field or source reference when possible. If a requested tool was blocked or failed, state that as an information gap. Recommended consequential actions remain proposals requiring human authorization.
"""


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


async def tool_aware_situation_analysis(
    session: Session,
    *,
    question: str,
    tenant_id: str = "default",
    situation_id: Optional[str] = None,
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
    allow_mutating_tools: bool = False,
) -> Dict[str, Any]:
    catalog = tool_catalog()
    planner = await complete_json(
        system_prompt=TOOL_PLANNER_POLICY,
        user_payload={
            "operator_question": question,
            "tenant_id": tenant_id,
            "situation_id": situation_id,
            "allow_mutating_tools": allow_mutating_tools,
            "tool_catalog": catalog,
        },
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
        temperature=0.0,
    )

    requested_calls = list(planner.get("tool_calls") or [])[:5]
    # A situation question should always anchor to the authoritative record when scoped.
    if situation_id and not any(str(c.get("tool_name")) == "situation_snapshot" for c in requested_calls):
        requested_calls.insert(0, {"tool_name": "situation_snapshot", "arguments": {}, "reason": "Anchor analysis to authoritative situation record"})
        requested_calls = requested_calls[:5]

    trace: List[Dict[str, Any]] = []
    for index, call in enumerate(requested_calls, start=1):
        tool_name = str(call.get("tool_name") or "").strip()
        if not tool_name:
            continue
        try:
            executed = execute_tool(
                session,
                tool_name=tool_name,
                arguments=dict(call.get("arguments") or {}),
                tenant_id=tenant_id,
                situation_id=situation_id,
                allow_mutating_tools=allow_mutating_tools,
            )
            trace.append({"step": index, "reason": call.get("reason"), **executed})
        except Exception as exc:  # Tool failure becomes evidence, not an orchestration crash.
            trace.append({
                "step": index,
                "tool_name": tool_name,
                "status": "failed",
                "reason": call.get("reason"),
                "error": str(exc),
            })

    synthesis = await complete_json(
        system_prompt=TOOL_SYNTHESIS_POLICY,
        user_payload={
            "operator_question": question,
            "tenant_id": tenant_id,
            "situation_id": situation_id,
            "tool_planner_summary": planner.get("reasoning_summary"),
            "tool_trace": trace,
        },
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
        temperature=0.1,
    )
    return {
        "analysis": synthesis,
        "tool_trace": trace,
        "planner": {
            "reasoning_summary": planner.get("reasoning_summary"),
            "requested_tool_count": len(requested_calls),
        },
        "policy": {
            "tool_aware": True,
            "read_only_tools_auto_allowed": True,
            "mutating_tools_allowed": allow_mutating_tools,
            "deterministic_tools_are_authoritative": True,
            "human_authorization_required_for_consequential_actions": True,
        },
    }


async def generate_briefing(
    session: Session,
    *,
    situation_id: str,
    audience: str = "operator",
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
) -> Dict[str, Any]:
    analysis = await tool_aware_situation_analysis(
        session,
        question="Produce the current operational picture, important changes, risks, resource concerns and information gaps.",
        tenant_id="default",
        situation_id=situation_id,
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
        allow_mutating_tools=False,
    )
    raw = await complete_json(
        system_prompt=ORCHESTRATOR_POLICY + "\nRole: Briefing Agent. Produce a concise operational briefing from supplied SitRep analysis. Return {headline,situation,key_changes,risks,resource_state,decisions_required,information_gaps,confidence}. Do not introduce facts absent from the supplied analysis/tool evidence.",
        user_payload={"audience": audience, "analysis": analysis},
        data_classification=data_classification,
        preferred_provider=preferred_provider,
        require_sovereign=require_sovereign,
    )
    return {"situation_id": situation_id, "audience": audience, "briefing": raw, "tool_trace": analysis.get("tool_trace", [])}


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
    allow_mutating_tools: bool = False,
) -> Dict[str, Any]:
    intent = classify_intent(question)
    request_payload = {
        "question": question,
        "tenant_id": tenant_id,
        "situation_id": situation_id,
        "candidate_plan": candidate_plan,
        "intent": intent,
        "allow_mutating_tools": allow_mutating_tools,
    }

    if intent in {"situation", "coa", "red-team", "briefing"} and not situation_id:
        raise ValueError(f"situation_id is required for intent={intent}")

    if intent == "situation":
        result = await tool_aware_situation_analysis(
            session,
            question=question,
            tenant_id=tenant_id,
            situation_id=situation_id,
            data_classification=data_classification,
            preferred_provider=preferred_provider,
            require_sovereign=require_sovereign,
            allow_mutating_tools=allow_mutating_tools,
        )
    elif intent == "coa":
        # Existing COA planner already consumes deterministic forecast + optimizer data.
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

    provider_id = None
    model_name = None
    confidence = 0.5
    evidence: List[Dict[str, Any]] = []
    assumptions: List[str] = []
    contradictions: List[str] = []
    information_gaps: List[str] = []
    if isinstance(result, dict):
        candidate = result.get("analysis") if isinstance(result.get("analysis"), dict) else result
        provider_id = candidate.get("model_provider") if isinstance(candidate, dict) else None
        model_name = candidate.get("model_name") if isinstance(candidate, dict) else None
        confidence = float(candidate.get("confidence") or 0.5) if isinstance(candidate, dict) else 0.5
        evidence = list(candidate.get("evidence") or []) if isinstance(candidate, dict) else []
        assumptions = [str(x) for x in candidate.get("assumptions") or []] if isinstance(candidate, dict) else []
        contradictions = [str(x) for x in candidate.get("contradictions") or []] if isinstance(candidate, dict) else []
        information_gaps = [str(x) for x in candidate.get("information_gaps") or []] if isinstance(candidate, dict) else []

    run = record_ai_run(
        session,
        role=f"orchestrator:{intent}",
        request_payload=request_payload,
        response_payload=result if isinstance(result, dict) else {"result": result},
        tenant_id=tenant_id,
        situation_id=situation_id,
        provider_id=provider_id,
        model_name=model_name,
        data_classification=data_classification,
        sovereign_required=require_sovereign,
        input_refs=[{"type": "situation", "id": situation_id}] if situation_id else [],
        evidence=evidence,
        assumptions=assumptions,
        contradictions=contradictions,
        information_gaps=information_gaps,
        confidence=confidence,
        agent_version="2.0",
    )
    return {
        "intent": intent,
        "answer": result,
        "ai_run_id": run.id,
        "policy": {
            "advisory_only": True,
            "deterministic_core_is_source_of_truth": True,
            "tool_trace_persisted_in_ai_run": True,
            "human_authorization_required_for_consequential_actions": True,
        },
    }
