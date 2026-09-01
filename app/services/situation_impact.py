from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.models.infrastructure import InfrastructureFeature
from app.models.situation import SituationAudit, SituationRecord
from app.services.dependency_graph import analyze_dependency_cascade
from app.services.situation_correlation import haversine_km, severity_from_scores


def analyze_situation_infrastructure_impact(
    session: Session,
    situation_id: str,
    radius_km: Optional[float] = None,
    max_depth: int = 4,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise ValueError("Situation not found")
    if situation.latitude is None or situation.longitude is None:
        raise ValueError("Situation has no geographic position")

    impact_radius = float(radius_km or max(situation.radius_km, 25.0))
    statement = select(InfrastructureFeature).where(InfrastructureFeature.tenant_id == situation.tenant_id)
    if categories:
        statement = statement.where(InfrastructureFeature.category.in_(categories))
    features = list(session.exec(statement).all())

    direct_impacts: List[Dict[str, Any]] = []
    cascade_paths: List[Dict[str, Any]] = []
    max_direct_score = 0.0
    max_cascade_score = 0.0

    for feature in features:
        if feature.centroid_latitude is None or feature.centroid_longitude is None:
            continue
        distance = haversine_km(
            situation.latitude,
            situation.longitude,
            feature.centroid_latitude,
            feature.centroid_longitude,
        )
        if distance > impact_radius:
            continue

        distance_factor = max(0.0, 1.0 - (distance / max(impact_radius, 0.001)))
        direct_score = min(
            1.0,
            distance_factor
            * (0.55 + (0.25 * feature.criticality_score) + (0.20 * feature.vulnerability_score)),
        )
        max_direct_score = max(max_direct_score, direct_score)
        direct_impacts.append({
            "feature_id": feature.id,
            "category": feature.category,
            "subtype": feature.subtype,
            "name": feature.name,
            "distance_km": round(distance, 2),
            "direct_impact_score": round(direct_score, 4),
            "source_system": feature.source_system,
            "source_id": feature.source_id,
        })

        cascade = analyze_dependency_cascade(
            session=session,
            tenant_id=situation.tenant_id,
            seed_type="infrastructure",
            seed_id=feature.id,
            max_depth=max_depth,
        )
        for path in cascade.get("impact_paths", []):
            combined_score = direct_score * float(path.get("propagated_impact_score") or 0.0)
            max_cascade_score = max(max_cascade_score, combined_score)
            cascade_paths.append({
                "seed_feature_id": feature.id,
                "seed_feature_name": feature.name,
                **path,
                "situation_impact_score": round(combined_score, 4),
            })

    direct_impacts.sort(key=lambda item: (-item["direct_impact_score"], item["distance_km"]))
    cascade_paths.sort(key=lambda item: (-item["situation_impact_score"], item["depth"]))

    previous_risk = situation.risk_score
    previous_urgency = situation.urgency_score
    infrastructure_signal = max(max_direct_score, max_cascade_score)
    if direct_impacts:
        situation.risk_score = min(1.0, max(situation.risk_score, 0.45) + (0.25 * infrastructure_signal))
        situation.urgency_score = min(1.0, max(situation.urgency_score, 0.45) + (0.20 * infrastructure_signal))
        situation.severity = severity_from_scores(situation.risk_score, situation.urgency_score)

    impact_context = {
        "radius_km": impact_radius,
        "direct_feature_count": len(direct_impacts),
        "cascade_path_count": len(cascade_paths),
        "max_direct_score": round(max_direct_score, 4),
        "max_cascade_score": round(max_cascade_score, 4),
        "top_direct_impacts": direct_impacts[:25],
        "top_cascade_impacts": cascade_paths[:50],
        "method": "centroid screening + explicit dependency cascade",
        "limitations": [
            "Centroid screening is operational triage, not geometric intersection modelling.",
            "Cascade propagation uses explicit dependency edges only.",
        ],
    }
    situation.context = {**(situation.context or {}), "infrastructure_impact": impact_context}
    session.add(situation)
    session.add(SituationAudit(
        situation_id=situation.id,
        action="infrastructure_impact_analyzed",
        note=f"{len(direct_impacts)} nearby infrastructure features; {len(cascade_paths)} cascade paths",
        payload={
            "previous_risk": previous_risk,
            "new_risk": situation.risk_score,
            "previous_urgency": previous_urgency,
            "new_urgency": situation.urgency_score,
            **impact_context,
        },
    ))
    session.commit()
    session.refresh(situation)

    return {
        "situation_id": situation.id,
        "severity": situation.severity,
        "risk_score": situation.risk_score,
        "urgency_score": situation.urgency_score,
        "direct_impacts": direct_impacts,
        "cascade_impacts": cascade_paths,
        "analysis": impact_context,
    }
