from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from app.services.ai.association_model import MODEL_PATH, load_model_bundle


router = APIRouter(prefix="/api/v1/model", tags=["model"])


def get_model_metadata() -> Dict[str, Any]:
    model_exists = MODEL_PATH.exists()
    model_size_kb = round(MODEL_PATH.stat().st_size / 1024, 2) if model_exists else None

    bundle = load_model_bundle()

    if bundle:
        model_name = bundle.get("model_name")
        model_version = bundle.get("model_version")
        model_type = bundle.get("model_type")
        features = bundle.get("features", [])
    else:
        model_name = "sitrep_association_model_fallback"
        model_version = "0.1.0"
        model_type = "deterministic_fallback"
        features = []

    return {
        "model_available": bool(model_exists and bundle is not None),
        "model_name": model_name,
        "model_version": model_version,
        "model_type": model_type,
        "model_file": str(MODEL_PATH),
        "model_size_kb": model_size_kb,
        "features": features,
    }


@router.get("/evaluation")
async def read_model_evaluation():
    metadata = get_model_metadata()

    return {
        "status": "ok",
        **metadata,
        "training_data": {
            "training_mode": "synthetic_maritime_isr_observation_pairs",
            "positive_examples": 5000,
            "negative_examples": 5000,
            "total_examples": 10000,
            "label_definition": "same_entity",
            "data_sensitivity": "synthetic_unclassified",
            "purpose": (
                "TRL 4 prototype validation of learned association scoring across "
                "heterogeneous observation types."
            ),
        },
        "validation_summary": {
            "validation_type": "synthetic_holdout_validation",
            "operational_claim": (
                "Synthetic validation only. Metrics are not claimed as operational CAF performance."
            ),
            "expected_behavior": [
                "high score for plausible same-entity observations",
                "lower score for ambiguous observations",
                "rejection support for impossible movement or mismatched observations",
                "fallback operation when trained model file is unavailable",
            ],
        },
        "feature_groups": {
            "spatiotemporal": [
                "distance_km",
                "time_delta_seconds",
                "estimated_speed_knots",
                "gate_passed",
            ],
            "source_quality": [
                "input_confidence",
                "existing_entity_confidence",
                "source_trust_weight",
            ],
            "classification_and_modality": [
                "object_type_match",
                "source_type_code",
                "entity_type_code",
            ],
            "kinematic": [
                "heading_delta",
                "speed_delta",
            ],
        },
        "demonstrated_scenarios": [
            {
                "name": "Scenario A: Maritime ISR Vessel Track",
                "endpoint": "/api/v1/demo/vessel-track",
                "modalities": ["radar", "eo_video", "rf_detection", "text_report"],
                "object_type": "vessel",
            },
            {
                "name": "Scenario B: Arctic ISR Fusion",
                "endpoint": "/api/v1/demo/arctic-isr",
                "modalities": ["satellite", "rf_detection", "telemetry", "text_report"],
                "object_type": "vessel",
            },
            {
                "name": "Scenario C: Airborne Multi-Sensor Track",
                "endpoint": "/api/v1/demo/airborne-track",
                "modalities": ["radar", "eo_ir", "telemetry", "text_report"],
                "object_type": "aircraft",
            },
            {
                "name": "Adversarial Impossible-Movement Rejection",
                "endpoint": "/api/v1/demo/adversarial-track",
                "modalities": ["radar", "eo_video", "rf_detection"],
                "object_type": "vessel",
            },
        ],
        "edge_profile": {
            "runs_locally": True,
            "requires_cloud_ai": False,
            "model_runtime": "scikit-learn/joblib",
            "suitable_for_edge_prototype": True,
            "fallback_available": True,
        },
        "limitations": [
            "Current trained model uses synthetic data only.",
            "Operational validation requires representative ISR/C2 datasets.",
            "Current model is lightweight and tabular; Component 1b will mature toward richer multimodal and temporal models.",
            "Current classification policy layer is prototype-only and does not perform real cross-domain downgrade.",
        ],
    }


@router.get("/card")
async def read_model_card():
    metadata = get_model_metadata()

    return {
        "status": "ok",
        "model_card": {
            "model_name": metadata["model_name"],
            "model_version": metadata["model_version"],
            "model_type": metadata["model_type"],
            "model_available": metadata["model_available"],
            "intended_use": (
                "Estimate whether a new heterogeneous observation should be associated "
                "with an existing operational entity/track."
            ),
            "not_intended_for": [
                "autonomous targeting",
                "weapons-release decisions",
                "classified release decisions",
                "standalone operational deployment without validation",
            ],
            "inputs": {
                "observation_features": metadata["features"],
                "supported_modalities": [
                    "radar",
                    "eo_video",
                    "eo_ir",
                    "rf_detection",
                    "satellite",
                    "telemetry",
                    "text_report",
                    "sonar",
                ],
            },
            "outputs": {
                "learned_model_score": "Probability-like association score from local trained model.",
                "baseline_score": "Rule/baseline fusion score.",
                "ai_score": "Blend of baseline and learned score.",
                "final_score": "Fusion confidence used in outputs.",
                "uncertainty_score": "1 - final_score.",
                "uncertainty_level": "low / medium / high.",
            },
            "explainability": [
                "confidence_drivers",
                "uncertainty_drivers",
                "source_trust_weight",
                "spatiotemporal gate status",
                "provenance processing steps",
            ],
            "safety_and_governance": [
                "human-in-the-loop operator review supported",
                "policy context recorded in provenance",
                "classification_in/classification_out captured",
                "release_decision recorded",
                "source lineage preserved",
            ],
            "known_limitations": [
                "Synthetic training data only at current stage.",
                "Requires operational validation with representative datasets.",
                "May require calibration per sensor type, domain, and mission environment.",
            ],
            "component_1b_maturation_path": [
                "expand synthetic scenario generator",
                "train multimodal temporal association model",
                "calibrate confidence and uncertainty scores",
                "evaluate against realistic ISR/C2 datasets",
                "package lightweight ONNX/runtime model for tactical edge",
                "validate policy-aware provenance and operator trust workflows",
            ],
        },
    }
@router.get("/card")
async def read_model_card():
    metadata = get_model_metadata()

    return {
        "status": "ok",
        "model_card": {
            "model_name": metadata["model_name"],
            "model_version": metadata["model_version"],
            "model_type": metadata["model_type"],
            "model_available": metadata["model_available"],
            "model_size_kb": metadata["model_size_kb"],
            "intended_use": (
                "Estimate whether a new heterogeneous observation should be associated "
                "with an existing operational entity or track."
            ),
            "not_intended_for": [
                "autonomous targeting",
                "weapons-release decisions",
                "classified release decisions",
                "standalone operational deployment without validation",
            ],
            "inputs": {
                "observation_features": metadata["features"],
                "supported_modalities": [
                    "radar",
                    "eo_video",
                    "eo_ir",
                    "rf_detection",
                    "satellite",
                    "telemetry",
                    "text_report",
                    "sonar",
                ],
            },
            "outputs": {
                "learned_model_score": "Probability-like association score from the local trained model.",
                "baseline_score": "Rule/baseline fusion score.",
                "ai_score": "Blend of baseline and learned score.",
                "final_score": "Fusion confidence used in SitRep outputs.",
                "uncertainty_score": "1 - final_score.",
                "uncertainty_level": "low / medium / high.",
            },
            "explainability": [
                "confidence_drivers",
                "uncertainty_drivers",
                "source_trust_weight",
                "spatiotemporal gate status",
                "provenance processing steps",
            ],
            "safety_and_governance": [
                "human-in-the-loop operator review supported",
                "policy context recorded in provenance",
                "classification_in and classification_out captured",
                "release_decision recorded",
                "source lineage preserved",
            ],
            "training_data": {
                "training_mode": "synthetic_maritime_isr_pairs",
                "positive_examples": 5000,
                "negative_examples": 5000,
                "total_examples": 10000,
                "data_sensitivity": "synthetic_unclassified",
            },
            "known_limitations": [
                "Synthetic training data only at current stage.",
                "Requires operational validation with representative ISR/C2 datasets.",
                "May require calibration per sensor type, domain, and mission environment.",
            ],
            "component_1b_maturation_path": [
                "expand synthetic scenario generator",
                "train multimodal temporal association model",
                "calibrate confidence and uncertainty scores",
                "evaluate against realistic ISR/C2 datasets",
                "package lightweight ONNX/runtime model for tactical edge",
                "validate policy-aware provenance and operator trust workflows",
            ],
        },
    }
