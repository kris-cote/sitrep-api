from __future__ import annotations

from typing import Any, Dict, List


def build_allocation_summary(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the optimizer's detailed plan into a dashboard/operator-friendly view."""
    packages = plan.get("response_packages") or []
    proposals = plan.get("proposals") or []
    remaining = plan.get("remaining_capacity") or {}
    competing = plan.get("competing_resources") or {}

    incidents: List[Dict[str, Any]] = []
    for package in packages:
        resources = package.get("recommended_resources") or []
        severity = resources[0].get("severity") if resources else None
        incidents.append({
            "situation_id": package.get("situation_id"),
            "title": package.get("situation_title"),
            "severity": severity,
            "priority_score": package.get("priority_score"),
            "package_score": package.get("package_score"),
            "package_confidence": package.get("package_confidence"),
            "recommended_resource_count": len(resources),
            "missing_resource_groups": package.get("missing_resource_groups") or [],
            "decision": package.get("human_decision", "approve_modify_or_reject"),
        })
    incidents.sort(key=lambda x: -(x.get("priority_score") or 0.0))

    resources_by_id: Dict[str, Dict[str, Any]] = {}
    for p in proposals:
        cap_id = p.get("capability_id")
        if not cap_id:
            continue
        entry = resources_by_id.setdefault(cap_id, {
            "capability_id": cap_id,
            "resource_name": p.get("resource_name"),
            "resource_type": p.get("resource_type"),
            "resource_group": p.get("resource_group"),
            "allocations": [],
        })
        entry["allocations"].append({
            "situation_id": p.get("situation_id"),
            "situation_title": p.get("situation_title"),
            "priority_score": p.get("priority_score"),
            "proposed_fraction": p.get("proposed_fraction"),
            "distance_km": p.get("distance_km"),
            "candidate_score": p.get("candidate_score"),
        })

    resources: List[Dict[str, Any]] = []
    for cap_id, entry in resources_by_id.items():
        entry["allocations"].sort(key=lambda x: -(x.get("priority_score") or 0.0))
        entry["remaining_fraction"] = remaining.get(cap_id)
        entry["competing"] = cap_id in competing
        entry["competing_situation_ids"] = competing.get(cap_id, [])
        entry["proposed_total_fraction"] = round(sum(float(x.get("proposed_fraction") or 0.0) for x in entry["allocations"]), 4)
        resources.append(entry)
    resources.sort(key=lambda x: (not x["competing"], x.get("resource_group") or "", x.get("resource_name") or ""))

    gaps: List[Dict[str, Any]] = []
    for package in packages:
        missing = package.get("missing_resource_groups") or []
        if missing:
            gaps.append({
                "situation_id": package.get("situation_id"),
                "situation_title": package.get("situation_title"),
                "priority_score": package.get("priority_score"),
                "missing_resource_groups": missing,
            })
    for unmet in plan.get("unmet_situations") or []:
        gaps.append({
            "situation_id": unmet.get("situation_id"),
            "priority_score": unmet.get("priority_score"),
            "reason": unmet.get("reason"),
            "missing_resource_groups": [],
        })

    conflicts = []
    for cap_id, situation_ids in competing.items():
        resource = resources_by_id.get(cap_id, {})
        conflicts.append({
            "capability_id": cap_id,
            "resource_name": resource.get("resource_name"),
            "resource_group": resource.get("resource_group"),
            "situation_ids": situation_ids,
            "incident_count": len(situation_ids),
            "message": f"{len(situation_ids)} incidents are competing for {resource.get('resource_name') or cap_id}",
        })

    policy = plan.get("policy") or {}
    return {
        "tenant_id": plan.get("tenant_id"),
        "overview": {
            "active_situations": plan.get("active_situation_count", 0),
            "available_capabilities": plan.get("capability_count", 0),
            "active_allocations": plan.get("active_allocation_count", 0),
            "proposed_allocations": len(proposals),
            "resource_conflicts": len(conflicts),
            "capability_gaps": len(gaps),
        },
        "incident_priority": incidents,
        "resource_allocation": resources,
        "capability_gaps": gaps,
        "conflicts": conflicts,
        "decision_status": {
            "mode": "recommendation_only" if policy.get("proposal_only", True) else "allocation",
            "human_authorization_required": policy.get("human_authorization_required", True),
            "existing_allocations_preserved": policy.get("does_not_cancel_or_reassign_existing_allocations", True),
            "priority_ordering_applied": policy.get("higher_priority_situations_consume_shared_capacity_first", False),
            "operator_action": "approve_modify_or_reject",
        },
    }
