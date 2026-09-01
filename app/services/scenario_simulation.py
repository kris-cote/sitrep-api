from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.models.resource_capability import ResponseResourceCapability
from app.models.situation import SituationRecord
from app.services.operational_forecast import _forecast_priority, _resource_group
from app.services.resource_optimizer import _situation_priority


ALLOWED_RESOURCE_STATES = {"available", "limited", "committed", "maintenance", "unavailable", "unknown"}


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _apply_situation_changes(s: SituationRecord, changes: Dict[str, Any]) -> Dict[str, Any]:
    risk = _bounded(changes.get("risk_score", s.risk_score or 0.0))
    urgency = _bounded(changes.get("urgency_score", s.urgency_score or 0.0))
    severity = str(changes.get("severity", s.severity or "low"))
    radius_km = max(0.0, float(changes.get("radius_km", s.radius_km or 0.0)))
    context = deepcopy(s.context or {})
    context.update(changes.get("context", {}) or {})
    if "forecast_trend" in changes:
        context["forecast_trend"] = max(-1.0, min(1.0, float(changes["forecast_trend"])))
    return {
        "situation_id": s.id,
        "title": s.title,
        "domain": s.domain,
        "risk_score": risk,
        "urgency_score": urgency,
        "severity": severity,
        "radius_km": radius_km,
        "context": context,
    }


def _scenario_priority(item: Dict[str, Any]) -> float:
    severity_weight = {"low": 0.15, "moderate": 0.35, "medium": 0.35, "high": 0.70, "critical": 1.0}.get(str(item.get("severity") or "low").lower(), 0.25)
    return _bounded(0.45 * float(item.get("risk_score") or 0.0) + 0.40 * float(item.get("urgency_score") or 0.0) + 0.15 * severity_weight)


def _resource_effective_supply(cap: ResponseResourceCapability, override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    override = override or {}
    state = str(override.get("availability_status", cap.availability_status or "unknown")).lower()
    if state not in ALLOWED_RESOURCE_STATES:
        raise ValueError(f"Unsupported availability_status in scenario: {state}")
    availability = _bounded(override.get("availability_score", cap.availability_score or 0.5))
    readiness = _bounded(override.get("readiness_score", cap.readiness_score or 0.5))
    capacity = _bounded(override.get("capacity_score", cap.capacity_score or 0.5))
    suitability = _bounded(override.get("suitability_score", cap.suitability_score or 0.5))
    state_factor = {
        "available": 1.0,
        "limited": 0.65,
        "committed": 0.45,
        "maintenance": 0.25,
        "unavailable": 0.0,
        "unknown": 0.50,
    }[state]
    effective = availability * readiness * capacity * suitability * state_factor
    return {
        "capability_id": cap.id,
        "resource_group": _resource_group(cap),
        "availability_status": state,
        "effective_supply": round(_bounded(effective), 4),
    }


def simulate_scenario(
    session: Session,
    tenant_id: str = "default",
    situation_changes: Optional[List[Dict[str, Any]]] = None,
    resource_changes: Optional[List[Dict[str, Any]]] = None,
    infrastructure_changes: Optional[List[Dict[str, Any]]] = None,
    horizons_hours: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Run an in-memory what-if simulation without mutating persistent records."""
    situations = list(session.exec(
        select(SituationRecord)
        .where(SituationRecord.tenant_id == tenant_id)
        .where(SituationRecord.status == "active")
    ).all())
    capabilities = list(session.exec(
        select(ResponseResourceCapability).where(ResponseResourceCapability.tenant_id == tenant_id)
    ).all())

    situation_change_map = {str(item.get("situation_id")): item for item in (situation_changes or []) if item.get("situation_id")}
    resource_change_map = {str(item.get("capability_id")): item for item in (resource_changes or []) if item.get("capability_id")}

    baseline_priorities = {s.id: round(_situation_priority(s), 4) for s in situations}
    scenario_situations: List[Dict[str, Any]] = []
    for s in situations:
        scenario = _apply_situation_changes(s, situation_change_map.get(s.id, {}))
        scenario["baseline_priority"] = baseline_priorities[s.id]
        scenario["scenario_priority"] = round(_scenario_priority(scenario), 4)
        scenario["priority_delta"] = round(scenario["scenario_priority"] - baseline_priorities[s.id], 4)
        scenario_situations.append(scenario)

    baseline_supply: Dict[str, float] = {"air": 0.0, "fire": 0.0, "medical": 0.0, "shelter": 0.0, "general": 0.0}
    scenario_supply: Dict[str, float] = {"air": 0.0, "fire": 0.0, "medical": 0.0, "shelter": 0.0, "general": 0.0}
    resource_impacts: List[Dict[str, Any]] = []
    for cap in capabilities:
        base = _resource_effective_supply(cap)
        changed = _resource_effective_supply(cap, resource_change_map.get(cap.id))
        baseline_supply[base["resource_group"]] += float(base["effective_supply"])
        scenario_supply[changed["resource_group"]] += float(changed["effective_supply"])
        if base["resource_group"] != "general":
            baseline_supply["general"] += 0.25 * float(base["effective_supply"])
        if changed["resource_group"] != "general":
            scenario_supply["general"] += 0.25 * float(changed["effective_supply"])
        if base != changed:
            resource_impacts.append({
                "capability_id": cap.id,
                "resource_type": cap.resource_type,
                "baseline": base,
                "scenario": changed,
                "effective_supply_delta": round(float(changed["effective_supply"]) - float(base["effective_supply"]), 4),
            })

    horizons = sorted({float(h) for h in (horizons_hours or [0.5, 2.0, 6.0, 24.0]) if float(h) > 0})
    forecast: List[Dict[str, Any]] = []
    domain_mix = {
        "wildfire-emergency": {"fire": 0.90, "air": 0.70, "medical": 0.45, "shelter": 0.55, "general": 0.50},
        "canada-maritime-arctic": {"air": 0.65, "medical": 0.35, "general": 0.65},
        "critical-infrastructure": {"general": 0.75, "medical": 0.30, "shelter": 0.30},
        "general": {"general": 0.60, "medical": 0.30, "shelter": 0.25},
    }
    for horizon in horizons:
        demand = {"air": 0.0, "fire": 0.0, "medical": 0.0, "shelter": 0.0, "general": 0.0}
        for item in scenario_situations:
            trend = float((item.get("context") or {}).get("forecast_trend") or 0.0)
            horizon_factor = min(1.0, horizon / 12.0)
            forecast_priority = _bounded(float(item["scenario_priority"]) + 0.30 * trend * horizon_factor)
            mix = domain_mix.get(str(item.get("domain") or "general").lower(), domain_mix["general"])
            for group, weight in mix.items():
                demand[group] += forecast_priority * float(weight)
        groups: Dict[str, Any] = {}
        for group in demand:
            available = float(scenario_supply.get(group, 0.0))
            required = float(demand[group])
            gap = required - available
            groups[group] = {
                "forecast_demand_units": round(required, 4),
                "available_effective_units": round(available, 4),
                "gap_units": round(gap, 4),
                "shortage": gap > 0.10,
            }
        forecast.append({"horizon_hours": horizon, "groups": groups})

    infrastructure_impacts = []
    for change in infrastructure_changes or []:
        infrastructure_impacts.append({
            "feature_id": change.get("feature_id"),
            "assumed_state": change.get("state", "degraded"),
            "impact_type": change.get("impact_type", "availability"),
            "notes": change.get("notes"),
            "limitation": "Infrastructure scenario changes are recorded as assumptions; dependency/cascade propagation requires explicit dependency edges.",
        })

    scenario_situations.sort(key=lambda x: -float(x["scenario_priority"]))
    return {
        "tenant_id": tenant_id,
        "baseline": {
            "situation_priorities": baseline_priorities,
            "effective_supply_units": {k: round(v, 4) for k, v in baseline_supply.items()},
        },
        "scenario": {
            "situations": scenario_situations,
            "effective_supply_units": {k: round(v, 4) for k, v in scenario_supply.items()},
            "resource_impacts": resource_impacts,
            "infrastructure_assumptions": infrastructure_impacts,
            "forecast": forecast,
        },
        "policy": {
            "simulation_only": True,
            "persistent_data_mutated": False,
            "proposal_only": True,
            "human_authorization_required_for_real_actions": True,
        },
        "limitations": [
            "This is a deterministic what-if screening simulation, not a validated hazard-behaviour model.",
            "Infrastructure failures do not create or infer dependency relationships; only explicit authoritative dependency edges may drive cascades.",
            "Scenario results depend on the assumptions supplied by the operator and current SitRep data quality.",
        ],
    }
