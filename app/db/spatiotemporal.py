from datetime import datetime, timezone
from typing import Dict, Any, Optional
import math


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 999999.0

    radius_km = 6371.0

    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radius_km * c


def kmh_to_knots(kmh: float) -> float:
    return kmh * 0.539957


def parse_datetime(value) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, str):
        cleaned = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None

    return None


def max_allowed_speed_knots_for(entity_type: Optional[str]) -> float:
    """
    Conservative prototype thresholds.
    These are intentionally broad for demo use.
    Later this can become entity-class specific and policy/config driven.
    """
    speed_map = {
        "vessel": 60.0,
        "ship": 60.0,
        "small_vessel": 50.0,
        "aircraft": 700.0,
        "uav": 160.0,
        "vehicle": 180.0,
        "wildfire": 20.0,
        "unknown": 700.0,
    }

    return speed_map.get((entity_type or "unknown").lower(), 700.0)


def evaluate_spatiotemporal_gate(
    observation: Dict[str, Any],
    entity: Dict[str, Any],
) -> Dict[str, Any]:
    obs_time = parse_datetime(observation.get("collected_at"))
    ent_time = parse_datetime(entity.get("last_seen_at"))

    distance_km = haversine_km(
        observation.get("latitude"),
        observation.get("longitude"),
        entity.get("current_latitude"),
        entity.get("current_longitude"),
    )

    entity_type = observation.get("object_type") or entity.get("entity_type") or "unknown"
    max_allowed_speed_knots = max_allowed_speed_knots_for(entity_type)

    if obs_time is None or ent_time is None:
        return {
            "gate_passed": True,
            "gate_status": "unknown_time",
            "distance_km": round(distance_km, 4),
            "time_delta_seconds": None,
            "estimated_speed_knots": None,
            "max_allowed_speed_knots": max_allowed_speed_knots,
            "gate_reason": "Time comparison unavailable; allowing association with elevated uncertainty.",
        }

    time_delta_seconds = abs((obs_time - ent_time).total_seconds())

    if time_delta_seconds == 0:
        if distance_km <= 0.25:
            return {
                "gate_passed": True,
                "gate_status": "same_time_close_distance",
                "distance_km": round(distance_km, 4),
                "time_delta_seconds": time_delta_seconds,
                "estimated_speed_knots": 0.0,
                "max_allowed_speed_knots": max_allowed_speed_knots,
                "gate_reason": "Observation timestamp matches prior entity time and location is close.",
            }

        return {
            "gate_passed": False,
            "gate_status": "same_time_large_distance",
            "distance_km": round(distance_km, 4),
            "time_delta_seconds": time_delta_seconds,
            "estimated_speed_knots": None,
            "max_allowed_speed_knots": max_allowed_speed_knots,
            "gate_reason": "Observation has same timestamp but is too far from the existing entity location.",
        }

    hours = time_delta_seconds / 3600.0
    kmh = distance_km / hours
    estimated_speed_knots = kmh_to_knots(kmh)

    # Add a small tolerance so normal sensor noise does not split tracks.
    tolerance_factor = 1.25
    allowed_with_tolerance = max_allowed_speed_knots * tolerance_factor

    if estimated_speed_knots <= allowed_with_tolerance:
        return {
            "gate_passed": True,
            "gate_status": "kinematically_plausible",
            "distance_km": round(distance_km, 4),
            "time_delta_seconds": round(time_delta_seconds, 2),
            "estimated_speed_knots": round(estimated_speed_knots, 4),
            "max_allowed_speed_knots": max_allowed_speed_knots,
            "gate_reason": f"Movement is kinematically plausible for {entity_type} track.",
        }

    return {
        "gate_passed": False,
        "gate_status": "impossible_movement",
        "distance_km": round(distance_km, 4),
        "time_delta_seconds": round(time_delta_seconds, 2),
        "estimated_speed_knots": round(estimated_speed_knots, 4),
        "max_allowed_speed_knots": max_allowed_speed_knots,
        "gate_reason": (
            f"Observation would require approximately {round(estimated_speed_knots, 2)} knots, "
            f"which exceeds the allowed threshold for {entity_type}."
        ),
    }
