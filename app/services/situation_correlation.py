from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any, Dict, Optional, Tuple

from sqlmodel import Session, select

from app.models.situation import SituationAudit, SituationRecord
from app.services.mission_packs import get_mission_pack, select_mission_pack


DEFAULT_RADIUS_KM = 50.0
DEFAULT_TIME_WINDOW_HOURS = 24


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0088
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


def _domain_for_observation(observation: Dict[str, Any]) -> str:
    source_type = str(observation.get("source_type") or "").lower()
    object_type = str(observation.get("object_type") or "").lower()
    if source_type == "weather_alert" or "weather hazard" in object_type:
        return "wildfire-emergency"
    return select_mission_pack(observation)


def _find_candidate(
    session: Session,
    tenant_id: str,
    domain: str,
    observed_at: datetime,
    latitude: Optional[float],
    longitude: Optional[float],
    radius_km: float,
    time_window_hours: int,
) -> Tuple[Optional[SituationRecord], Optional[float]]:
    cutoff = observed_at - timedelta(hours=time_window_hours)
    candidates = session.exec(
        select(SituationRecord)
        .where(SituationRecord.tenant_id == tenant_id)
        .where(SituationRecord.domain == domain)
        .where(SituationRecord.status == "active")
        .where(SituationRecord.last_observed_at >= cutoff)
        .order_by(SituationRecord.last_observed_at.desc())
    ).all()

    if latitude is None or longitude is None:
        return (candidates[0], None) if candidates else (None, None)

    best: Optional[SituationRecord] = None
    best_distance: Optional[float] = None
    for candidate in candidates:
        if candidate.latitude is None or candidate.longitude is None:
            continue
        distance = haversine_km(latitude, longitude, candidate.latitude, candidate.longitude)
        allowed_radius = max(radius_km, candidate.radius_km)
        if distance <= allowed_radius and (best_distance is None or distance < best_distance):
            best = candidate
            best_distance = distance
    return best, best_distance


def _combined_scores(situation: SituationRecord, observation: Dict[str, Any], is_new_source: bool) -> Dict[str, float]:
    obs_confidence = float(observation.get("confidence") or 0.5)
    source_diversity_bonus = 0.12 if is_new_source else 0.0

    confidence = min(1.0, max(situation.confidence, obs_confidence) + source_diversity_bonus)
    risk = situation.risk_score
    urgency = situation.urgency_score

    text = " ".join(
        str(observation.get(key) or "")
        for key in ("object_type", "source_type", "source_system")
    ).lower()

    if any(term in text for term in ("wildfire", "active_fire", "fire", "smoke")):
        risk = max(risk, 0.65)
        urgency = max(urgency, 0.65)
    if any(term in text for term in ("wind", "warning", "watch", "weather alert", "weather hazard", "storm", "heat")):
        has_fire_context = any("fire" in item.lower() for item in situation.source_types)
        risk = min(1.0, max(risk, 0.55) + (0.15 if has_fire_context else 0.0))
        urgency = min(1.0, max(urgency, 0.55) + 0.10)
    if is_new_source:
        risk = min(1.0, risk + 0.08)
        urgency = min(1.0, urgency + 0.08)

    return {"confidence": confidence, "risk": risk, "urgency": urgency}


def severity_from_scores(risk: float, urgency: float) -> str:
    combined = max(risk, urgency)
    if combined >= 0.80:
        return "critical"
    if combined >= 0.65:
        return "high"
    if combined >= 0.45:
        return "medium"
    return "low"


def correlate_observation(
    session: Session,
    observation_id: str,
    observation: Dict[str, Any],
    radius_km: float = DEFAULT_RADIUS_KM,
    time_window_hours: int = DEFAULT_TIME_WINDOW_HOURS,
) -> Dict[str, Any]:
    tenant_id = str(observation.get("tenant_id") or "default")
    domain = _domain_for_observation(observation)
    pack = get_mission_pack(domain)
    observed_at = _as_datetime(observation.get("collected_at"))
    latitude = observation.get("latitude")
    longitude = observation.get("longitude")
    source_type = str(observation.get("source_type") or "unknown")

    situation, distance_km = _find_candidate(
        session=session,
        tenant_id=tenant_id,
        domain=domain,
        observed_at=observed_at,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        time_window_hours=time_window_hours,
    )

    created = situation is None
    if created:
        situation = SituationRecord(
            tenant_id=tenant_id,
            mission_id=observation.get("mission_id"),
            domain=domain,
            title=f"{pack.get('name')}: {observation.get('object_type') or 'operational situation'}",
            summary="Situation created from first correlated observation.",
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            confidence=float(observation.get("confidence") or 0.5),
            risk_score=0.35,
            urgency_score=0.35,
            source_types=[source_type],
            observation_ids=[observation_id],
            correlation_reasons=["first observation in new situation"],
            evidence=[{"observation_id": observation_id, "source_type": source_type}],
            context={"mission_pack": domain},
            last_observed_at=observed_at,
        )
        scores = _combined_scores(situation, observation, is_new_source=True)
        situation.confidence = scores["confidence"]
        situation.risk_score = scores["risk"]
        situation.urgency_score = scores["urgency"]
        situation.severity = severity_from_scores(scores["risk"], scores["urgency"])
        session.add(situation)
        session.flush()
        reason = "created new situation"
    else:
        is_new_source = source_type not in situation.source_types
        scores = _combined_scores(situation, observation, is_new_source=is_new_source)
        situation.confidence = scores["confidence"]
        situation.risk_score = scores["risk"]
        situation.urgency_score = scores["urgency"]
        situation.severity = severity_from_scores(scores["risk"], scores["urgency"])
        situation.last_observed_at = observed_at
        situation.updated_at = datetime.now(timezone.utc)
        if source_type not in situation.source_types:
            situation.source_types = [*situation.source_types, source_type]
        if observation_id not in situation.observation_ids:
            situation.observation_ids = [*situation.observation_ids, observation_id]
        reasons = list(situation.correlation_reasons)
        reasons.append(
            f"correlated by domain={domain}, time<={time_window_hours}h"
            + (f", distance={distance_km:.1f}km" if distance_km is not None else "")
        )
        situation.correlation_reasons = reasons[-20:]
        situation.evidence = [
            *situation.evidence[-49:],
            {"observation_id": observation_id, "source_type": source_type, "distance_km": distance_km},
        ]
        reason = "joined existing situation"

    session.add(situation)
    session.add(
        SituationAudit(
            situation_id=situation.id,
            observation_id=observation_id,
            action="created" if created else "correlated",
            note=reason,
            payload={
                "domain": domain,
                "source_type": source_type,
                "distance_km": distance_km,
                "risk_score": situation.risk_score,
                "urgency_score": situation.urgency_score,
                "severity": situation.severity,
            },
        )
    )
    session.commit()
    session.refresh(situation)

    return {
        "situation_id": situation.id,
        "created": created,
        "domain": situation.domain,
        "severity": situation.severity,
        "confidence": situation.confidence,
        "risk_score": situation.risk_score,
        "urgency_score": situation.urgency_score,
        "source_types": situation.source_types,
        "observation_count": len(situation.observation_ids),
        "distance_km": distance_km,
        "correlation_reason": reason,
    }
