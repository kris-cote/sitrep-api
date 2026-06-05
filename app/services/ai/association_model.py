from pathlib import Path
from typing import Dict, Any

import joblib


MODEL_PATH = Path(__file__).parent / "models" / "sitrep_association_model.joblib"


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _fallback_score(features: Dict[str, Any]) -> float:
    """
    Safe fallback if the trained model file is unavailable.
    Keeps SitRep operational in edge/degraded mode.
    """
    score = 0.0

    if features.get("gate_passed", 0) == 1:
        score += 0.35

    if features.get("object_type_match", 0) == 1:
        score += 0.25

    distance_km = float(features.get("distance_km") or 999)
    if distance_km <= 1:
        score += 0.20
    elif distance_km <= 5:
        score += 0.10

    score += 0.10 * float(features.get("input_confidence") or 0.5)
    score += 0.10 * float(features.get("source_trust_weight") or 0.75)

    return clamp(score)


def load_model_bundle():
    if not MODEL_PATH.exists():
        return None

    try:
        return joblib.load(MODEL_PATH)
    except Exception:
        return None


def predict_same_entity_probability(features: Dict[str, Any]) -> Dict[str, Any]:
    bundle = load_model_bundle()

    if bundle is None:
        fallback = _fallback_score(features)
        return {
            "model_name": "sitrep_association_model_fallback",
            "model_version": "0.1.0",
            "model_type": "deterministic_fallback",
            "model_available": False,
            "learned_model_score": round(fallback, 4),
        }

    model = bundle["model"]
    feature_names = bundle["features"]

    row = [[float(features.get(name, 0.0) or 0.0) for name in feature_names]]

    probability = float(model.predict_proba(row)[0][1])

    return {
        "model_name": bundle["model_name"],
        "model_version": bundle["model_version"],
        "model_type": bundle["model_type"],
        "model_available": True,
        "learned_model_score": round(probability, 4),
    }
