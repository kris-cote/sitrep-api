from typing import Dict, Any, List

from app.services.ai.association_model import predict_same_entity_probability


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def calculate_uncertainty_level(score: float) -> str:
    if score <= 0.20:
        return "low"
    if score <= 0.45:
        return "medium"
    return "high"


def get_confidence_drivers(
    observation: Dict[str, Any],
    association_score: float,
    source_trust_weight: float = 0.80,
    learned_model_available: bool = False,
) -> List[str]:
    drivers = []

    if association_score >= 0.85:
        drivers.append("strong spatial/type association with existing track")
    elif association_score >= 0.60:
        drivers.append("moderate association with existing track")
    else:
        drivers.append("weak association or new track creation")

    if observation.get("distance_km") is not None:
        drivers.append("real spatiotemporal distance feature available")

    if observation.get("estimated_speed_knots") is not None:
        drivers.append("real kinematic speed estimate available")

    if source_trust_weight >= 0.85:
        drivers.append("high-trust source weighting")
    elif source_trust_weight >= 0.65:
        drivers.append("moderate-trust source weighting")
    else:
        drivers.append("low-trust source weighting")

    if learned_model_available:
        drivers.append("local learned association model available")

    return drivers


def source_trust_weight_for(source_type: str, source_system: str | None = None) -> float:
    trust_by_type = {
        "radar": 0.88,
        "eo_video": 0.90,
        "eo_ir": 0.90,
        "rf_detection": 0.78,
        "sigint": 0.78,
        "operator_report": 0.70,
        "text_report": 0.70,
        "telemetry": 0.84,
        "satellite": 0.86,
        "sonar": 0.76,
        "unknown": 0.75,
    }

    return trust_by_type.get(source_type or "unknown", 0.75)


def source_type_code_for(source_type: str | None) -> int:
    return {
        "radar": 0,
        "eo_video": 1,
        "rf_detection": 2,
        "text_report": 3,
        "telemetry": 4,
        "satellite": 5,
        "sonar": 6,
    }.get(source_type or "unknown", 99)


def entity_type_code_for(entity_type: str | None) -> int:
    return {
        "vessel": 0,
        "aircraft": 1,
        "uav": 2,
        "vehicle": 3,
    }.get(entity_type or "unknown", 99)


def as_float(value, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def score_multimodal_fusion_model(
    observation: Dict[str, Any],
    association_score: float,
    association: str,
    source_trust_weight: float | None = None,
) -> Dict[str, Any]:
    source_type = observation.get("source_type") or "unknown"
    source_system = observation.get("source_system")
    object_type = observation.get("object_type") or "unknown"
    input_confidence = as_float(observation.get("confidence"), 0.5)

    source_trust = (
        float(source_trust_weight)
        if source_trust_weight is not None
        else source_trust_weight_for(source_type, source_system)
    )

    distance_km = observation.get("distance_km")
    time_delta_seconds = observation.get("time_delta_seconds")
    estimated_speed_knots = observation.get("estimated_speed_knots")
    gate_passed = observation.get("gate_passed", True)
    gate_status = observation.get("gate_status")
    gate_reason = observation.get("gate_reason")

    baseline_score = clamp(
        (association_score * 0.55)
        + (input_confidence * 0.30)
        + (source_trust * 0.15)
    )

    learned_features = {
        "distance_km": as_float(distance_km, 0.5),
        "time_delta_seconds": as_float(time_delta_seconds, 60.0),
        "estimated_speed_knots": as_float(estimated_speed_knots, 10.0),
        "object_type_match": as_float(observation.get("object_type_match"), 1.0),
        "gate_passed": 1.0 if gate_passed else 0.0,
        "input_confidence": input_confidence,
        "existing_entity_confidence": as_float(
            observation.get("existing_entity_confidence"),
            baseline_score,
        ),
        "source_trust_weight": source_trust,
        "source_type_code": source_type_code_for(source_type),
        "entity_type_code": entity_type_code_for(object_type),
        "heading_delta": as_float(observation.get("heading_delta"), 10.0),
        "speed_delta": as_float(observation.get("speed_delta"), 5.0),
    }

    learned_result = predict_same_entity_probability(learned_features)
    learned_model_score = as_float(learned_result.get("learned_model_score"), baseline_score)

    ai_score = clamp(
        (baseline_score * 0.45)
        + (learned_model_score * 0.55)
    )

    final_score = clamp(
        (baseline_score * 0.40)
        + (ai_score * 0.60)
    )

    uncertainty_score = round(clamp(1.0 - final_score), 4)
    uncertainty_level = calculate_uncertainty_level(uncertainty_score)

    confidence_drivers = get_confidence_drivers(
        observation=observation,
        association_score=association_score,
        source_trust_weight=source_trust,
        learned_model_available=bool(learned_result.get("model_available")),
    )

    uncertainty_drivers = []

    if source_type in ["rf_detection", "sigint"]:
        uncertainty_drivers.append(
            "RF/SIGINT observation supports presence but does not provide visual confirmation"
        )

    if input_confidence < 0.80:
        uncertainty_drivers.append("input confidence below high-confidence threshold")

    if association_score >= 0.85:
        uncertainty_drivers.append(
            "track association uncertainty reduced by strong spatial/type match"
        )

    if source_trust < 0.80:
        uncertainty_drivers.append(
            "source trust weight contributes to residual uncertainty"
        )

    if gate_status:
        uncertainty_drivers.append(f"spatiotemporal gate status: {gate_status}")

    if not learned_result.get("model_available"):
        uncertainty_drivers.append(
            "trained local association model unavailable; deterministic fallback used"
        )

    if not uncertainty_drivers:
        uncertainty_drivers.append(
            "uncertainty primarily derived from source confidence and association score"
        )

    return {
        "model_name": "sitrep_fusion_model_v1",
        "model_version": "0.2.0",
        "model_type": "hybrid_baseline_plus_local_learned_association_model",
        "model_status": "trained_local_model_integrated_with_baseline_fusion",
        "input_modalities": [source_type],
        "source_system": source_system,
        "source_trust_weight": round(source_trust, 4),
        "input_confidence": round(input_confidence, 4),
        "baseline_score": round(baseline_score, 4),
        "learned_model_available": learned_result.get("model_available"),
        "learned_model_name": learned_result.get("model_name"),
        "learned_model_version": learned_result.get("model_version"),
        "learned_model_type": learned_result.get("model_type"),
        "learned_model_score": round(learned_model_score, 4),
        "distance_km": distance_km,
        "time_delta_seconds": time_delta_seconds,
        "estimated_speed_knots": estimated_speed_knots,
        "gate_status": gate_status,
        "gate_reason": gate_reason,
        "ai_score": round(ai_score, 4),
        "final_score": round(final_score, 4),
        "uncertainty_score": uncertainty_score,
        "uncertainty_level": uncertainty_level,
        "confidence_drivers": confidence_drivers,
        "uncertainty_drivers": uncertainty_drivers,
    }
