from __future__ import annotations

from math import atan2, cos, degrees, radians, sin
from typing import Any, Dict, List

from sqlmodel import Session, select

from app.models.exposure import ExposureAsset
from app.models.situation import SituationRecord
from app.services.situation_correlation import haversine_km


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = radians(lat1)
    p2 = radians(lat2)
    dlon = radians(lon2 - lon1)
    y = sin(dlon) * cos(p2)
    x = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dlon)
    return (degrees(atan2(y, x)) + 360.0) % 360.0


def angular_difference(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def wildfire_exposure_screen(
    session: Session,
    situation_id: str,
    wind_from_deg: float,
    wind_speed_kmh: float,
    horizon_hours: float = 6.0,
    tenant_id: str = "default",
) -> Dict[str, Any]:
    """Conservative screening projection, not a fire-behaviour forecast.

    It ranks exposure assets by whether they lie in a downwind corridor and by
    distance/criticality. It intentionally does not estimate flame-front spread;
    operational wildfire prediction should be supplied by an approved fire model.
    """
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise ValueError("Situation not found")
    if situation.latitude is None or situation.longitude is None:
        raise ValueError("Situation has no geographic location")

    downwind_bearing = (float(wind_from_deg) + 180.0) % 360.0
    # Screening radius grows with wind and time, capped to keep this a local triage tool.
    screening_radius_km = max(10.0, min(100.0, 10.0 + float(wind_speed_kmh) * 0.35 * max(1.0, float(horizon_hours))))
    corridor_half_angle = 45.0 if wind_speed_kmh >= 30 else 60.0

    assets = session.exec(select(ExposureAsset).where(ExposureAsset.tenant_id == tenant_id)).all()
    ranked: List[Dict[str, Any]] = []
    population_screened = 0
    for asset in assets:
        distance = haversine_km(situation.latitude, situation.longitude, asset.latitude, asset.longitude)
        if distance > screening_radius_km:
            continue
        bearing = bearing_deg(situation.latitude, situation.longitude, asset.latitude, asset.longitude)
        angle = angular_difference(bearing, downwind_bearing)
        in_corridor = angle <= corridor_half_angle
        if not in_corridor:
            continue

        distance_factor = max(0.0, 1.0 - distance / screening_radius_km)
        alignment_factor = max(0.0, 1.0 - angle / corridor_half_angle)
        score = min(
            1.0,
            0.35 * distance_factor
            + 0.25 * alignment_factor
            + 0.25 * float(asset.criticality_score)
            + 0.15 * float(asset.vulnerability_score),
        )
        if asset.population:
            population_screened += int(asset.population)
        ranked.append(
            {
                "asset_id": asset.id,
                "name": asset.name,
                "asset_type": asset.asset_type,
                "distance_km": round(distance, 2),
                "bearing_deg": round(bearing, 1),
                "off_downwind_axis_deg": round(angle, 1),
                "screening_score": round(score, 3),
                "population": asset.population,
                "criticality_score": asset.criticality_score,
                "vulnerability_score": asset.vulnerability_score,
            }
        )

    ranked.sort(key=lambda item: item["screening_score"], reverse=True)
    result = {
        "situation_id": situation_id,
        "method": "wind-aligned exposure screening",
        "not_a_fire_behaviour_forecast": True,
        "wind_from_deg": float(wind_from_deg) % 360.0,
        "downwind_bearing_deg": downwind_bearing,
        "wind_speed_kmh": float(wind_speed_kmh),
        "horizon_hours": float(horizon_hours),
        "screening_radius_km": round(screening_radius_km, 1),
        "corridor_half_angle_deg": corridor_half_angle,
        "population_in_screening_corridor": population_screened,
        "assets_in_screening_corridor": len(ranked),
        "assets": ranked[:100],
    }
    situation.context = {**(situation.context or {}), "wildfire_exposure_screen": result}
    if ranked:
        top = ranked[0]["screening_score"]
        situation.risk_score = min(1.0, max(situation.risk_score, 0.55 + 0.35 * top))
        situation.urgency_score = min(1.0, max(situation.urgency_score, 0.50 + 0.35 * top))
    session.add(situation)
    session.commit()
    return result
