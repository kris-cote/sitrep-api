import math
import random
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split


MODEL_DIR = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / "sitrep_association_model.joblib"


SOURCE_TYPE_MAP = {
    "radar": 0,
    "eo_video": 1,
    "rf_detection": 2,
    "text_report": 3,
    "telemetry": 4,
    "satellite": 5,
    "sonar": 6,
    "unknown": 99,
}


ENTITY_TYPE_MAP = {
    "vessel": 0,
    "aircraft": 1,
    "uav": 2,
    "vehicle": 3,
    "unknown": 99,
}


SOURCE_TRUST = {
    "radar": 0.88,
    "eo_video": 0.90,
    "rf_detection": 0.78,
    "text_report": 0.70,
    "telemetry": 0.84,
    "satellite": 0.86,
    "sonar": 0.76,
    "unknown": 0.75,
}


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def kmh_to_knots(kmh: float) -> float:
    return kmh * 0.539957


def generate_positive_example():
    """
    Same entity: close in time/space and physically plausible.
    """
    source_type = random.choice(["radar", "eo_video", "rf_detection", "text_report"])
    entity_type = "vessel"

    time_delta_seconds = random.uniform(15, 300)
    # Vessels generally plausible under ~60 knots, but use broad spread.
    true_speed_knots = random.uniform(2, 35)
    distance_km = (true_speed_knots / 0.539957) * (time_delta_seconds / 3600)

    # Add sensor noise.
    distance_km += random.uniform(0, 0.2)

    estimated_speed_knots = kmh_to_knots(distance_km / (time_delta_seconds / 3600))
    object_type_match = 1
    gate_passed = 1

    input_confidence = random.uniform(0.65, 0.95)
    existing_entity_confidence = random.uniform(0.65, 0.98)
    source_trust_weight = SOURCE_TRUST[source_type]

    heading_delta = random.uniform(0, 25)
    speed_delta = random.uniform(0, 8)

    return {
        "distance_km": distance_km,
        "time_delta_seconds": time_delta_seconds,
        "estimated_speed_knots": estimated_speed_knots,
        "object_type_match": object_type_match,
        "gate_passed": gate_passed,
        "input_confidence": input_confidence,
        "existing_entity_confidence": existing_entity_confidence,
        "source_trust_weight": source_trust_weight,
        "source_type_code": SOURCE_TYPE_MAP[source_type],
        "entity_type_code": ENTITY_TYPE_MAP[entity_type],
        "heading_delta": heading_delta,
        "speed_delta": speed_delta,
        "same_entity": 1,
    }


def generate_negative_example():
    """
    Different entity: far away, impossible movement, wrong type, or low-confidence mismatch.
    """
    source_type = random.choice(["radar", "eo_video", "rf_detection", "text_report"])
    entity_type = random.choice(["vessel", "aircraft", "unknown"])

    scenario = random.choice(["far", "impossible_speed", "wrong_type", "weak_low_confidence"])

    if scenario == "far":
        time_delta_seconds = random.uniform(30, 600)
        distance_km = random.uniform(15, 250)
        object_type_match = 1
        gate_passed = 0

    elif scenario == "impossible_speed":
        time_delta_seconds = random.uniform(30, 180)
        distance_km = random.uniform(20, 150)
        object_type_match = 1
        gate_passed = 0

    elif scenario == "wrong_type":
        time_delta_seconds = random.uniform(30, 300)
        distance_km = random.uniform(0.1, 2.5)
        object_type_match = 0
        gate_passed = 1

    else:
        time_delta_seconds = random.uniform(30, 300)
        distance_km = random.uniform(3, 8)
        object_type_match = random.choice([0, 1])
        gate_passed = random.choice([0, 1])

    estimated_speed_knots = kmh_to_knots(distance_km / (time_delta_seconds / 3600))

    input_confidence = random.uniform(0.25, 0.75)
    existing_entity_confidence = random.uniform(0.25, 0.80)
    source_trust_weight = SOURCE_TRUST[source_type]

    heading_delta = random.uniform(30, 180)
    speed_delta = random.uniform(10, 80)

    return {
        "distance_km": distance_km,
        "time_delta_seconds": time_delta_seconds,
        "estimated_speed_knots": estimated_speed_knots,
        "object_type_match": object_type_match,
        "gate_passed": gate_passed,
        "input_confidence": input_confidence,
        "existing_entity_confidence": existing_entity_confidence,
        "source_trust_weight": source_trust_weight,
        "source_type_code": SOURCE_TYPE_MAP[source_type],
        "entity_type_code": ENTITY_TYPE_MAP.get(entity_type, 99),
        "heading_delta": heading_delta,
        "speed_delta": speed_delta,
        "same_entity": 0,
    }


def build_dataset(n_positive=5000, n_negative=5000):
    rows = []

    for _ in range(n_positive):
        rows.append(generate_positive_example())

    for _ in range(n_negative):
        rows.append(generate_negative_example())

    random.shuffle(rows)
    return pd.DataFrame(rows)


def train():
    random.seed(42)
    np.random.seed(42)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = build_dataset()

    features = [
        "distance_km",
        "time_delta_seconds",
        "estimated_speed_knots",
        "object_type_match",
        "gate_passed",
        "input_confidence",
        "existing_entity_confidence",
        "source_trust_weight",
        "source_type_code",
        "entity_type_code",
        "heading_delta",
        "speed_delta",
    ]

    X = df[features]
    y = df["same_entity"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    model = RandomForestClassifier(
        n_estimators=150,
        max_depth=8,
        random_state=42,
        class_weight="balanced",
    )

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]

    print("=== SitRep Association Model v1 ===")
    print(classification_report(y_test, predictions))
    print(f"ROC AUC: {roc_auc_score(y_test, probabilities):.4f}")

    bundle = {
        "model_name": "sitrep_association_model_v1",
        "model_version": "0.1.0",
        "model_type": "random_forest_association_classifier",
        "features": features,
        "source_type_map": SOURCE_TYPE_MAP,
        "entity_type_map": ENTITY_TYPE_MAP,
        "model": model,
    }

    joblib.dump(bundle, MODEL_PATH)
    print(f"Saved model to: {MODEL_PATH}")


if __name__ == "__main__":
    train()
