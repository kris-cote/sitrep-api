from __future__ import annotations

from typing import Any, Dict, List


def evaluate_decision_trigger(
    observation: Dict[str, Any],
    tracking: Dict[str, Any],
    fusion: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate whether newly fused information merits decision analysis.

    This stage is deliberately deterministic and explainable. It never executes
    an action; it only produces a trigger recommendation for the decision layer.
    """
    reasons: List[str] = []
    confidence = float(observation.get("confidence") or 0.5)
    association_score = float(tracking.get("association_score") or 0.0)
    gate_result = tracking.get("gate_result")
    classification = str(observation.get("classification_tag") or "UNCLASSIFIED")
    object_type = str(observation.get("object_type") or "unknown")

    severity = "low"

    if confidence >= 0.8:
        reasons.append("high-confidence observation")

    if association_score < 0.45:
        reasons.append("low entity-association confidence")

    if gate_result in {False, "fail", "failed", "reject", "rejected"}:
        reasons.append("tracking gate anomaly")
        severity = "high"

    lowered_type = object_type.lower()
    if any(term in lowered_type for term in ("fire", "smoke", "distress", "intrusion", "unknown", "anomaly", "hazard")):
        reasons.append(f"decision-relevant object type: {object_type}")
        if severity == "low":
            severity = "medium"

    if classification.upper() not in {"UNCLASSIFIED", "PUBLIC"}:
        reasons.append("restricted information handling required")

    # Fusion implementations may expose their own alert/anomaly indicators.
    fusion_alert = fusion.get("alert") or fusion.get("anomaly") or fusion.get("requires_attention")
    if fusion_alert:
        reasons.append("fusion layer marked situation for attention")
        severity = "high"

    should_trigger = len(reasons) >= 2 or severity == "high"

    return {
        "should_trigger": should_trigger,
        "severity": severity,
        "reasons": reasons,
        "human_authorization_required": True,
        "next_step": "generate_course_of_action" if should_trigger else "continue_monitoring",
    }
