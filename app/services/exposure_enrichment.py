from __future__ import annotations

from typing import Any, Dict, List

from sqlmodel import Session, select

from app.models.exposure import ExposureAsset
from app.models.situation import SituationAudit, SituationRecord
from app.services.situation_correlation import haversine_km, severity_from_scores


def _distance_factor(distance_km: float, radius_km: float) -> float:
    if radius_km <= 0:
        return 0.0
    return max(0.0, 1.0 - min(distance_km / radius_km, 1.0))


def enrich_situation_exposure(
    session: Session,
    situation_id: str,
    radius_km: float | None = None,
) -> Dict[str, Any]:
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise ValueError("Situation not found")
    if situation.latitude is None or situation.longitude is None:
        return {
            "situation_id": situation.id,
            "asset_count": 0,
            "assets": [],
            "population_exposed": 0,
            "exposure_score": 0.0,
            "risk_score": situation.risk_score,
            "urgency_score": situation.urgency_score,
            "severity": situation.severity,
            "note": "Situation has no geospatial centroid",
        }

    search_radius = float(radius_km or max(situation.radius_km, 25.0))
    assets = session.exec(
        select(ExposureAsset).where(ExposureAsset.tenant_id == situation.tenant_id)
    ).all()

    exposed: List[Dict[str, Any]] = []
    population_exposed = 0
    weighted_scores: List[float] = []

    for asset in assets:
        distance = haversine_km(
            situation.latitude,
            situation.longitude,
            asset.latitude,
            asset.longitude,
        )
        if distance > search_radius:
            continue
        factor = _distance_factor(distance, search_radius)
        asset_score = min(
            1.0,
            factor * (0.55 * float(asset.criticality_score) + 0.45 * float(asset.vulnerability_score)),
        )
        weighted_scores.append(asset_score)
        if asset.population:
            population_exposed += max(0, int(asset.population))
        exposed.append(
            {
                "asset_id": asset.id,
                "asset_type": asset.asset_type,
                "name": asset.name,
                "distance_km": round(distance, 2),
                "criticality_score": asset.criticality_score,
                "vulnerability_score": asset.vulnerability_score,
                "population": asset.population,
                "exposure_score": round(asset_score, 4),
                "source_system": asset.source_system,
            }
        )

    exposed.sort(key=lambda item: (item["distance_km"], -item["exposure_score"]))
    top_score = max(weighted_scores, default=0.0)
    diversity_bonus = min(0.15, len({item["asset_type"] for item in exposed}) * 0.03)
    population_bonus = 0.0
    if population_exposed >= 100000:
        population_bonus = 0.20
    elif population_exposed >= 10000:
        population_bonus = 0.15
    elif population_exposed >= 1000:
        population_bonus = 0.10
    elif population_exposed > 0:
        population_bonus = 0.05

    exposure_score = min(1.0, top_score + diversity_bonus + population_bonus)
    new_risk = min(1.0, max(situation.risk_score, exposure_score) + (0.10 if exposure_score >= 0.65 else 0.0))
    new_urgency = min(1.0, max(situation.urgency_score, exposure_score * 0.9))
    new_severity = severity_from_scores(new_risk, new_urgency)

    situation.risk_score = new_risk
    situation.urgency_score = new_urgency
    situation.severity = new_severity
    context = dict(situation.context or {})
    context["exposure"] = {
        "search_radius_km": search_radius,
        "asset_count": len(exposed),
        "population_exposed": population_exposed,
        "exposure_score": exposure_score,
        "assets": exposed[:50],
    }
    situation.context = context
    session.add(situation)
    session.add(
        SituationAudit(
            situation_id=situation.id,
            action="exposure_enriched",
            note=f"Evaluated {len(exposed)} exposed assets within {search_radius:.1f} km",
            payload={
                "asset_count": len(exposed),
                "population_exposed": population_exposed,
                "exposure_score": exposure_score,
                "risk_score": new_risk,
                "urgency_score": new_urgency,
                "severity": new_severity,
            },
        )
    )
    session.commit()
    session.refresh(situation)

    return {
        "situation_id": situation.id,
        "asset_count": len(exposed),
        "assets": exposed,
        "population_exposed": population_exposed,
        "exposure_score": exposure_score,
        "risk_score": situation.risk_score,
        "urgency_score": situation.urgency_score,
        "severity": situation.severity,
    }
