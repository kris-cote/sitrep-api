from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from sqlmodel import Session

from app.models.situation import SituationRecord
from app.services.exposure_enrichment import enrich_situation_exposure
from app.services.resource_availability import situation_resource_profile
from app.services.resource_optimizer import optimize_resource_plan
from app.services.operational_forecast import forecast_operational_demand
from app.services.scenario_comparison import compare_scenarios
from app.services.situation_impact import analyze_situation_infrastructure_impact


ToolHandler = Callable[..., Dict[str, Any]]


def _serialize_situation(session: Session, *, situation_id: str, **_: Any) -> Dict[str, Any]:
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
        "latitude": item.latitude,
        "longitude": item.longitude,
        "radius_km": item.radius_km,
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
        "updated_at": item.updated_at,
    }


def _forecast(session: Session, *, tenant_id: str = "default", horizons_hours: Optional[List[float]] = None, **_: Any) -> Dict[str, Any]:
    return forecast_operational_demand(session, tenant_id=tenant_id, horizons_hours=horizons_hours)


def _optimizer(session: Session, *, tenant_id: str = "default", **_: Any) -> Dict[str, Any]:
    return optimize_resource_plan(session, tenant_id=tenant_id)


def _resource_profile(session: Session, *, situation_id: str, tenant_id: Optional[str] = None, radius_km: Optional[float] = None, **_: Any) -> Dict[str, Any]:
    return situation_resource_profile(session=session, situation_id=situation_id, tenant_id=tenant_id, radius_km=radius_km)


def _exposure(session: Session, *, situation_id: str, radius_km: Optional[float] = None, **_: Any) -> Dict[str, Any]:
    return enrich_situation_exposure(session=session, situation_id=situation_id, radius_km=radius_km)


def _infrastructure(session: Session, *, situation_id: str, radius_km: Optional[float] = None, max_depth: int = 4, categories: Optional[List[str]] = None, **_: Any) -> Dict[str, Any]:
    return analyze_situation_infrastructure_impact(
        session=session,
        situation_id=situation_id,
        radius_km=radius_km,
        max_depth=max_depth,
        categories=categories,
    )


def _scenario_compare(session: Session, *, tenant_id: str = "default", branches: List[Dict[str, Any]], horizons_hours: Optional[List[float]] = None, weights: Optional[Dict[str, float]] = None, **_: Any) -> Dict[str, Any]:
    return compare_scenarios(
        session=session,
        tenant_id=tenant_id,
        branches=branches,
        horizons_hours=horizons_hours,
        weights=weights,
    )


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "situation_snapshot": {
        "description": "Read the authoritative current SitRep situation record, evidence, scores and context.",
        "mutates_state": False,
        "requires_situation_id": True,
        "handler": _serialize_situation,
        "arguments": {"situation_id": "string"},
    },
    "operational_forecast": {
        "description": "Read deterministic future resource demand, shortages and pre-staging signals.",
        "mutates_state": False,
        "requires_situation_id": False,
        "handler": _forecast,
        "arguments": {"tenant_id": "string", "horizons_hours": "optional list[number]"},
    },
    "resource_optimizer": {
        "description": "Read the deterministic multi-incident resource allocation proposal and conflicts.",
        "mutates_state": False,
        "requires_situation_id": False,
        "handler": _optimizer,
        "arguments": {"tenant_id": "string"},
    },
    "situation_resources": {
        "description": "Read nearby response resources and capability feasibility for one situation.",
        "mutates_state": False,
        "requires_situation_id": True,
        "handler": _resource_profile,
        "arguments": {"situation_id": "string", "tenant_id": "optional string", "radius_km": "optional number"},
    },
    "scenario_comparison": {
        "description": "Run deterministic A/B/C scenario comparison using supplied structured branches.",
        "mutates_state": False,
        "requires_situation_id": False,
        "handler": _scenario_compare,
        "arguments": {"tenant_id": "string", "branches": "list[scenario branch]", "horizons_hours": "optional list[number]", "weights": "optional object"},
    },
    "exposure_enrichment": {
        "description": "Calculate nearby population/facility exposure and update the situation exposure context/audit.",
        "mutates_state": True,
        "requires_situation_id": True,
        "handler": _exposure,
        "arguments": {"situation_id": "string", "radius_km": "optional number"},
    },
    "infrastructure_impact": {
        "description": "Calculate direct/cascade infrastructure impact and update situation context/audit.",
        "mutates_state": True,
        "requires_situation_id": True,
        "handler": _infrastructure,
        "arguments": {"situation_id": "string", "radius_km": "optional number", "max_depth": "optional integer", "categories": "optional list[string]"},
    },
}


def tool_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "mutates_state": bool(spec["mutates_state"]),
            "requires_situation_id": bool(spec["requires_situation_id"]),
            "arguments": spec["arguments"],
        }
        for name, spec in TOOL_REGISTRY.items()
    ]


def execute_tool(
    session: Session,
    *,
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    tenant_id: str = "default",
    situation_id: Optional[str] = None,
    allow_mutating_tools: bool = False,
) -> Dict[str, Any]:
    spec = TOOL_REGISTRY.get(tool_name)
    if not spec:
        raise ValueError(f"Unknown SitRep tool: {tool_name}")
    if spec["mutates_state"] and not allow_mutating_tools:
        return {
            "tool_name": tool_name,
            "status": "blocked",
            "reason": "Tool mutates situation state/audit and requires explicit allow_mutating_tools=true",
            "mutates_state": True,
        }

    args = dict(arguments or {})
    args.setdefault("tenant_id", tenant_id)
    if spec["requires_situation_id"]:
        resolved_id = args.get("situation_id") or situation_id
        if not resolved_id:
            raise ValueError(f"situation_id is required for tool={tool_name}")
        args["situation_id"] = resolved_id

    # Do not allow an AI-generated tenant/situation identifier to silently switch
    # the caller's explicitly scoped context.
    if situation_id:
        args["situation_id"] = situation_id if spec["requires_situation_id"] else args.get("situation_id")
    args["tenant_id"] = tenant_id

    handler: ToolHandler = spec["handler"]
    result = handler(session, **args)
    return {
        "tool_name": tool_name,
        "status": "completed",
        "mutates_state": bool(spec["mutates_state"]),
        "arguments": {k: v for k, v in args.items() if k not in {"session"}},
        "result": result,
    }
