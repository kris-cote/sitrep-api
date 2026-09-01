from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.models.exposure import ExposureAsset
from app.models.resource_allocation import ResponseResourceAllocation
from app.models.resource_capability import ResponseResourceCapability
from app.models.situation import SituationRecord
from app.services.resource_allocation import ACTIVE_STATUSES
from app.services.resource_availability import STATUS_FACTOR, _capability_score


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _situation_priority(s: SituationRecord) -> float:
    severity_weight = {"low": 0.15, "moderate": 0.35, "medium": 0.35, "high": 0.70, "critical": 1.0}.get((s.severity or "low").lower(), 0.25)
    return max(0.0, min(1.0, 0.45 * float(s.risk_score or 0.0) + 0.40 * float(s.urgency_score or 0.0) + 0.15 * severity_weight))


def _capability_group(cap: ResponseResourceCapability) -> str:
    text = " ".join([cap.resource_type or "", cap.name or "", " ".join(cap.capabilities or [])]).lower()
    if any(x in text for x in ("helicopter", "aircraft", "aviation", "rotary", "fixed wing", "airbase")):
        return "air"
    if any(x in text for x in ("fire", "suppression", "engine", "crew")):
        return "fire"
    if any(x in text for x in ("medical", "ambulance", "hospital", "medevac")):
        return "medical"
    if any(x in text for x in ("shelter", "reception")):
        return "shelter"
    return "general"


def optimize_resource_plan(
    session: Session,
    tenant_id: str = "default",
    max_distance_km: float = 300.0,
    max_situations: int = 100,
    max_candidates_per_situation: int = 10,
) -> Dict[str, Any]:
    situations = list(session.exec(
        select(SituationRecord)
        .where(SituationRecord.tenant_id == tenant_id)
        .where(SituationRecord.status == "active")
        .order_by(SituationRecord.updated_at.desc())
        .limit(max_situations)
    ).all())
    assets = {a.id: a for a in session.exec(select(ExposureAsset).where(ExposureAsset.tenant_id == tenant_id)).all()}
    caps = list(session.exec(select(ResponseResourceCapability).where(ResponseResourceCapability.tenant_id == tenant_id)).all())
    allocations = list(session.exec(select(ResponseResourceAllocation).where(ResponseResourceAllocation.tenant_id == tenant_id)).all())

    committed: Dict[str, float] = {}
    active_by_cap: Dict[str, List[ResponseResourceAllocation]] = {}
    for a in allocations:
        if a.status not in ACTIVE_STATUSES:
            continue
        committed[a.capability_id] = committed.get(a.capability_id, 0.0) + max(0.0, min(1.0, float(a.allocated_fraction)))
        active_by_cap.setdefault(a.capability_id, []).append(a)

    ranked_situations = sorted(situations, key=lambda s: (-_situation_priority(s), -float(s.urgency_score or 0.0), -float(s.risk_score or 0.0)))
    remaining = {c.id: max(0.0, 1.0 - committed.get(c.id, 0.0)) for c in caps}
    proposals: List[Dict[str, Any]] = []
    unmet: List[Dict[str, Any]] = []

    for s in ranked_situations:
        if s.latitude is None or s.longitude is None:
            unmet.append({"situation_id": s.id, "reason": "missing_geolocation", "priority_score": round(_situation_priority(s), 4)})
            continue
        candidates: List[Dict[str, Any]] = []
        for cap in caps:
            asset = assets.get(cap.exposure_asset_id)
            if not asset:
                continue
            distance = _haversine_km(s.latitude, s.longitude, asset.latitude, asset.longitude)
            if distance > max_distance_km:
                continue
            rem = remaining.get(cap.id, 0.0)
            base_cap_score = _capability_score(cap, committed_fraction=1.0 - rem)
            distance_score = max(0.0, 1.0 - distance / max(max_distance_km, 1.0))
            status_score = STATUS_FACTOR.get((cap.availability_status or "unknown").lower(), 0.5)
            reassign_penalty = 0.20 if active_by_cap.get(cap.id) else 0.0
            score = (
                0.42 * _situation_priority(s)
                + 0.28 * base_cap_score
                + 0.18 * distance_score
                + 0.12 * status_score
                - reassign_penalty
            )
            candidates.append({
                "capability_id": cap.id,
                "exposure_asset_id": cap.exposure_asset_id,
                "resource_type": cap.resource_type,
                "resource_group": _capability_group(cap),
                "resource_name": cap.name,
                "distance_km": round(distance, 2),
                "remaining_fraction": round(rem, 4),
                "current_committed_fraction": round(1.0 - rem, 4),
                "candidate_score": round(max(0.0, min(1.0, score)), 4),
                "reassignment_required": bool(active_by_cap.get(cap.id)),
                "active_assignments": [a.assignment_name for a in active_by_cap.get(cap.id, [])],
            })
        candidates.sort(key=lambda x: (-x["candidate_score"], x["distance_km"]))
        candidates = candidates[:max_candidates_per_situation]
        usable = [c for c in candidates if c["remaining_fraction"] > 0.0 and c["candidate_score"] > 0.15]
        if not usable:
            unmet.append({"situation_id": s.id, "reason": "no_suitable_remaining_capability", "priority_score": round(_situation_priority(s), 4), "candidates": candidates})
            continue
        best = usable[0]
        suggested_fraction = min(0.50, max(0.10, 0.20 + 0.35 * _situation_priority(s)))
        allocated_fraction = min(best["remaining_fraction"], suggested_fraction)
        remaining[best["capability_id"]] = max(0.0, remaining[best["capability_id"]] - allocated_fraction)
        proposals.append({
            "situation_id": s.id,
            "situation_title": s.title,
            "severity": s.severity,
            "priority_score": round(_situation_priority(s), 4),
            "capability_id": best["capability_id"],
            "resource_name": best["resource_name"],
            "resource_type": best["resource_type"],
            "distance_km": best["distance_km"],
            "proposed_fraction": round(allocated_fraction, 4),
            "candidate_score": best["candidate_score"],
            "reassignment_required": best["reassignment_required"],
            "active_assignments": best["active_assignments"],
            "requires_human_authorization": True,
        })

    return {
        "tenant_id": tenant_id,
        "active_situation_count": len(situations),
        "capability_count": len(caps),
        "active_allocation_count": sum(1 for a in allocations if a.status in ACTIVE_STATUSES),
        "proposals": proposals,
        "unmet_situations": unmet,
        "remaining_capacity": {k: round(v, 4) for k, v in remaining.items()},
        "policy": {
            "proposal_only": True,
            "human_authorization_required": True,
            "does_not_cancel_or_reassign_existing_allocations": True,
            "reassignment_penalty_applied": True,
        },
    }
