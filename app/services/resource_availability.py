from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlmodel import Session, select

from app.models.exposure import ExposureAsset
from app.models.resource_allocation import ResponseResourceAllocation
from app.models.resource_capability import ResponseResourceCapability
from app.models.situation import SituationRecord


RESOURCE_GROUPS = {
    "air": {"emergency_airbase", "heliport", "airport"},
    "fire": {"fire_station", "emergency_facility"},
    "medical": {"hospital", "health_facility", "care_facility"},
    "shelter": {"shelter", "reception_centre", "emergency_facility"},
    "general": {"fire_station", "emergency_facility", "emergency_airbase", "heliport", "airport", "hospital", "health_facility", "shelter", "reception_centre"},
}

STATUS_FACTOR = {
    "available": 1.0,
    "limited": 0.65,
    "committed": 0.45,
    "maintenance": 0.25,
    "unavailable": 0.0,
    "unknown": 0.50,
}

ACTIVE_ALLOCATION_STATUSES = {"planned", "active"}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _asset_score(asset: ExposureAsset, distance_km: float, radius_km: float) -> float:
    distance_factor = max(0.0, 1.0 - (distance_km / max(radius_km, 1.0)))
    quality = 0.60 * max(0.0, min(1.0, float(asset.criticality_score))) + 0.40 * max(0.0, min(1.0, 1.0 - float(asset.vulnerability_score)))
    return max(0.0, min(1.0, 0.60 * distance_factor + 0.40 * quality))


def _capability_score(cap: ResponseResourceCapability, committed_fraction: float = 0.0) -> float:
    now = datetime.now(timezone.utc)
    if cap.valid_from and cap.valid_from > now:
        return 0.0
    if cap.valid_until and cap.valid_until < now:
        return 0.0
    status = STATUS_FACTOR.get((cap.availability_status or "unknown").lower(), 0.5)
    intrinsic = (
        0.30 * float(cap.availability_score)
        + 0.25 * float(cap.readiness_score)
        + 0.20 * float(cap.capacity_score)
        + 0.25 * float(cap.suitability_score)
    )
    remaining_capacity = max(0.0, 1.0 - max(0.0, committed_fraction))
    allocation_factor = 0.35 + 0.65 * remaining_capacity
    return max(0.0, min(1.0, intrinsic * status * allocation_factor))


def situation_resource_profile(
    session: Session,
    situation_id: str,
    radius_km: Optional[float] = None,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise ValueError("Situation not found")
    if situation.latitude is None or situation.longitude is None:
        return {
            "situation_id": situation_id,
            "resource_confidence": 0.0,
            "groups": {},
            "nearby_resources": [],
            "note": "Situation has no geolocation; resource feasibility could not be assessed.",
        }

    effective_radius = float(radius_km or max(50.0, float(situation.radius_km or 25.0) * 2.0))
    tenant = tenant_id or situation.tenant_id
    assets = list(session.exec(select(ExposureAsset).where(ExposureAsset.tenant_id == tenant)).all())
    capabilities = list(session.exec(select(ResponseResourceCapability).where(ResponseResourceCapability.tenant_id == tenant)).all())
    allocations = list(session.exec(select(ResponseResourceAllocation).where(ResponseResourceAllocation.tenant_id == tenant)).all())

    caps_by_asset: Dict[str, List[ResponseResourceCapability]] = {}
    for cap in capabilities:
        caps_by_asset.setdefault(cap.exposure_asset_id, []).append(cap)

    committed_by_capability: Dict[str, float] = {}
    for allocation in allocations:
        if allocation.status not in ACTIVE_ALLOCATION_STATUSES:
            continue
        committed_by_capability[allocation.capability_id] = committed_by_capability.get(allocation.capability_id, 0.0) + max(0.0, min(1.0, float(allocation.allocated_fraction)))

    nearby: List[Dict[str, Any]] = []
    for asset in assets:
        if asset.asset_type not in RESOURCE_GROUPS["general"]:
            continue
        distance = _haversine_km(situation.latitude, situation.longitude, asset.latitude, asset.longitude)
        if distance > effective_radius:
            continue
        base_score = _asset_score(asset, distance, effective_radius)
        asset_caps = caps_by_asset.get(asset.id, [])
        cap_details = []
        if asset_caps:
            scored = []
            for cap in asset_caps:
                committed = committed_by_capability.get(cap.id, 0.0)
                score = _capability_score(cap, committed_fraction=committed)
                scored.append(score)
                cap_details.append({
                    "capability_id": cap.id,
                    "resource_type": cap.resource_type,
                    "name": cap.name,
                    "availability_status": cap.availability_status,
                    "capability_score": round(score, 4),
                    "committed_fraction": round(committed, 4),
                    "remaining_fraction": round(max(0.0, 1.0 - committed), 4),
                    "overcommitted": committed > 1.000001,
                    "capabilities": cap.capabilities,
                    "capacity": cap.capacity,
                    "suitability": cap.suitability,
                    "constraints": cap.constraints,
                    "source_system": cap.source_system,
                })
            capability_score = max(scored) if scored else 0.5
            combined = 0.45 * base_score + 0.55 * capability_score
            capability_confidence = min(1.0, 0.55 + 0.10 * len(asset_caps))
        else:
            capability_score = None
            combined = base_score
            capability_confidence = 0.25
        nearby.append({
            "asset_id": asset.id,
            "asset_type": asset.asset_type,
            "name": asset.name,
            "distance_km": round(distance, 2),
            "criticality_score": asset.criticality_score,
            "vulnerability_score": asset.vulnerability_score,
            "availability_score": round(max(0.0, min(1.0, combined)), 4),
            "base_presence_score": round(base_score, 4),
            "capability_score": round(capability_score, 4) if capability_score is not None else None,
            "capability_confidence": round(capability_confidence, 4),
            "capability_records": cap_details,
            "source_system": asset.source_system,
        })

    nearby.sort(key=lambda item: (-item["availability_score"], item["distance_km"]))
    groups: Dict[str, Dict[str, Any]] = {}
    for group, accepted_types in RESOURCE_GROUPS.items():
        matches = [item for item in nearby if item["asset_type"] in accepted_types]
        if matches:
            top = matches[:5]
            score = sum(float(item["availability_score"]) for item in top) / len(top)
            cap_conf = sum(float(item["capability_confidence"]) for item in top) / len(top)
            coverage_confidence = min(1.0, 0.35 + 0.08 * len(matches) + 0.35 * cap_conf)
        else:
            score = 0.25
            coverage_confidence = 0.20
        groups[group] = {
            "score": round(score, 4),
            "count": len(matches),
            "coverage_confidence": round(coverage_confidence, 4),
            "top_resources": matches[:5],
        }

    capability_record_count = sum(len(item["capability_records"]) for item in nearby)
    active_allocation_count = sum(1 for item in allocations if item.status in ACTIVE_ALLOCATION_STATUSES)
    overall_confidence = min(1.0, 0.25 + 0.05 * len(nearby) + 0.03 * capability_record_count) if nearby else 0.20
    return {
        "situation_id": situation_id,
        "radius_km": effective_radius,
        "resource_confidence": round(overall_confidence, 4),
        "capability_record_count": capability_record_count,
        "active_allocation_count": active_allocation_count,
        "groups": groups,
        "nearby_resources": nearby[:50],
        "note": "Feasibility accounts for capability, availability and current allocation pressure; missing public/authorized data is not proof that a resource is unavailable.",
    }


def required_resource_group(option: Dict[str, Any]) -> str:
    text = " ".join([
        str(option.get("name") or ""),
        str(option.get("description") or ""),
        " ".join(str(v) for v in option.get("expected_outcomes", []) or []),
    ]).lower()
    if any(term in text for term in ("aircraft", "aviation", "helicopter", "air support", "airborne")):
        return "air"
    if any(term in text for term in ("fire crew", "firefighting", "suppression", "fire service")):
        return "fire"
    if any(term in text for term in ("medical", "hospital", "casualty", "patient", "ambulance")):
        return "medical"
    if any(term in text for term in ("evacuat", "shelter", "reception centre", "reception center")):
        return "shelter"
    return "general"


def apply_resource_profile_to_options(options: Iterable[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    groups = profile.get("groups") or {}
    confidence = float(profile.get("resource_confidence") or 0.0)
    for raw in options:
        option = dict(raw)
        group = required_resource_group(option)
        group_info = groups.get(group) or groups.get("general") or {"score": 0.5, "count": 0, "coverage_confidence": 0.0}
        assessed = float(group_info.get("score") or 0.0)
        original = float(option.get("resource_score", 0.5))
        effective_confidence = min(confidence, float(group_info.get("coverage_confidence") or confidence))
        adjusted = original * (1.0 - 0.65 * effective_confidence) + assessed * (0.65 * effective_confidence)
        option["resource_score"] = round(max(0.0, min(1.0, adjusted)), 4)
        metadata = dict(option.get("metadata") or {})
        metadata["resource_availability"] = {
            "required_group": group,
            "assessed_score": round(assessed, 4),
            "coverage_confidence": round(effective_confidence, 4),
            "nearby_count": int(group_info.get("count") or 0),
            "capability_record_count": int(profile.get("capability_record_count") or 0),
            "active_allocation_count": int(profile.get("active_allocation_count") or 0),
            "top_resources": group_info.get("top_resources", [])[:3],
        }
        option["metadata"] = metadata
        rationale = list(option.get("rationale") or [])
        rationale.append(f"resource_group={group}; allocation_aware_availability={assessed:.2f}; coverage_confidence={effective_confidence:.2f}")
        option["rationale"] = rationale
        result.append(option)
    return result
