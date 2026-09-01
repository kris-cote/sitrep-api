from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlmodel import Session

from app.services.scenario_simulation import simulate_scenario

DEFAULT_WEIGHTS = {
    "risk_reduction": 0.32,
    "resource_efficiency": 0.20,
    "reversibility": 0.16,
    "operational_continuity": 0.16,
    "confidence": 0.16,
}


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _avg_priority(sim: Dict[str, Any]) -> float:
    items = sim.get("scenario", {}).get("situations", []) or []
    if not items:
        return 0.0
    return sum(float(x.get("scenario_priority") or 0.0) for x in items) / len(items)


def _shortage_burden(sim: Dict[str, Any]) -> float:
    total = 0.0
    count = 0
    for horizon in sim.get("scenario", {}).get("forecast", []) or []:
        for group in (horizon.get("groups") or {}).values():
            gap = max(0.0, float(group.get("gap_units") or 0.0))
            total += min(1.0, gap)
            count += 1
    return 0.0 if count == 0 else min(1.0, total / count)


def _resource_change_burden(branch: Dict[str, Any]) -> float:
    changes = branch.get("resource_changes") or []
    if not changes:
        return 0.0
    burden = 0.0
    for item in changes:
        state = str(item.get("availability_status") or "").lower()
        state_cost = {"unavailable": 1.0, "maintenance": 0.8, "committed": 0.65, "limited": 0.45, "unknown": 0.30, "available": 0.05}.get(state, 0.25)
        readiness_cost = 1.0 - _bounded(item.get("readiness_score", 1.0)) if "readiness_score" in item else 0.0
        capacity_cost = 1.0 - _bounded(item.get("capacity_score", 1.0)) if "capacity_score" in item else 0.0
        burden += max(state_cost, readiness_cost, capacity_cost)
    return min(1.0, burden / len(changes))


def _reversibility(branch: Dict[str, Any]) -> float:
    explicit = branch.get("reversibility_score")
    if explicit is not None:
        return _bounded(explicit)
    infra = branch.get("infrastructure_changes") or []
    resources = branch.get("resource_changes") or []
    situation = branch.get("situation_changes") or []
    penalty = 0.08 * len(situation) + 0.10 * len(resources) + 0.14 * len(infra)
    return _bounded(1.0 - min(0.85, penalty))


def _continuity(branch: Dict[str, Any]) -> float:
    explicit = branch.get("operational_continuity_score")
    if explicit is not None:
        return _bounded(explicit)
    infra = branch.get("infrastructure_changes") or []
    disruptive = 0
    for item in infra:
        state = str(item.get("state") or "degraded").lower()
        if state in {"closed", "failed", "offline", "unavailable"}:
            disruptive += 1
    return _bounded(1.0 - min(0.9, 0.20 * disruptive + 0.05 * max(0, len(infra) - disruptive)))


def _confidence(sim: Dict[str, Any], branch: Dict[str, Any]) -> float:
    explicit = branch.get("confidence")
    if explicit is not None:
        return _bounded(explicit)
    assumptions = len(branch.get("situation_changes") or []) + len(branch.get("resource_changes") or []) + len(branch.get("infrastructure_changes") or [])
    return _bounded(0.88 - 0.04 * assumptions)


def compare_scenarios(
    session: Session,
    branches: List[Dict[str, Any]],
    tenant_id: str = "default",
    horizons_hours: Optional[List[float]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    if len(branches) < 2:
        raise ValueError("At least two scenario branches are required")
    if len(branches) > 10:
        raise ValueError("A maximum of 10 scenario branches may be compared at once")

    effective_weights = dict(DEFAULT_WEIGHTS)
    if weights:
        for key, value in weights.items():
            if key in effective_weights:
                effective_weights[key] = max(0.0, float(value))
    total = sum(effective_weights.values()) or 1.0
    effective_weights = {k: v / total for k, v in effective_weights.items()}

    results: List[Dict[str, Any]] = []
    baseline_priority: Optional[float] = None

    for index, branch in enumerate(branches, start=1):
        simulation = simulate_scenario(
            session=session,
            tenant_id=tenant_id,
            situation_changes=branch.get("situation_changes"),
            resource_changes=branch.get("resource_changes"),
            infrastructure_changes=branch.get("infrastructure_changes"),
            horizons_hours=horizons_hours,
        )
        current_avg = _avg_priority(simulation)
        if baseline_priority is None:
            baseline_values = list((simulation.get("baseline", {}).get("situation_priorities") or {}).values())
            baseline_priority = sum(float(v) for v in baseline_values) / len(baseline_values) if baseline_values else 0.0
        risk_reduction = _bounded((baseline_priority or 0.0) - current_avg + 0.5)
        shortage = _shortage_burden(simulation)
        change_burden = _resource_change_burden(branch)
        resource_efficiency = _bounded(1.0 - (0.65 * shortage + 0.35 * change_burden))
        reversibility = _reversibility(branch)
        continuity = _continuity(branch)
        confidence = _confidence(simulation, branch)

        score = (
            effective_weights["risk_reduction"] * risk_reduction
            + effective_weights["resource_efficiency"] * resource_efficiency
            + effective_weights["reversibility"] * reversibility
            + effective_weights["operational_continuity"] * continuity
            + effective_weights["confidence"] * confidence
        )

        results.append({
            "branch_id": str(branch.get("branch_id") or f"scenario-{index}"),
            "name": str(branch.get("name") or f"Scenario {index}"),
            "description": branch.get("description"),
            "score": round(_bounded(score), 4),
            "metrics": {
                "risk_reduction": round(risk_reduction, 4),
                "resource_efficiency": round(resource_efficiency, 4),
                "reversibility": round(reversibility, 4),
                "operational_continuity": round(continuity, 4),
                "confidence": round(confidence, 4),
                "average_scenario_priority": round(current_avg, 4),
                "forecast_shortage_burden": round(shortage, 4),
            },
            "simulation": simulation,
            "requires_human_authorization": True,
        })

    results.sort(key=lambda item: -float(item["score"]))
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank

    best = results[0]
    return {
        "tenant_id": tenant_id,
        "weights": {k: round(v, 4) for k, v in effective_weights.items()},
        "ranked_scenarios": results,
        "recommended_branch_id": best["branch_id"],
        "recommended_branch_name": best["name"],
        "recommendation_score": best["score"],
        "policy": {
            "simulation_only": True,
            "proposal_only": True,
            "persistent_data_mutated": False,
            "human_authorization_required_for_real_actions": True,
            "ranking_is_decision_support_not_automatic_execution": True,
        },
        "limitations": [
            "Scenario ranking depends on operator-supplied assumptions and available SitRep data quality.",
            "Risk reduction is a comparative screening metric, not a validated loss-estimation model.",
            "Weights should be calibrated by mission pack and operating authority before production use.",
        ],
    }
