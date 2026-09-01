from __future__ import annotations

from typing import Any, Dict, List


MISSION_PACKS: Dict[str, Dict[str, Any]] = {
    "canada-maritime-arctic": {
        "name": "Canada Maritime & Arctic",
        "domains": ["maritime", "arctic", "defence", "sar"],
        "description": "Canadian maritime and Arctic awareness, search-and-rescue, sovereignty, and operational coordination.",
        "weights": {
            "confidence": 0.25,
            "risk": 0.25,
            "urgency": 0.20,
            "resource": 0.10,
            "reversibility": 0.10,
            "policy": 0.10,
        },
        "default_options": [
            {
                "name": "Continue enhanced monitoring",
                "description": "Increase collection and maintain track continuity while gathering additional corroborating evidence.",
                "risk_score": 0.20,
                "urgency_score": 0.35,
                "resource_score": 0.85,
                "reversibility_score": 0.95,
                "policy_score": 1.0,
                "expected_outcomes": ["Improved confidence", "Reduced risk of premature escalation"],
                "rationale": ["Preserves optionality", "Prioritizes corroboration and provenance"],
            },
            {
                "name": "Task additional sensing",
                "description": "Request additional approved sensing or partner data to reduce uncertainty and refine the operational picture.",
                "risk_score": 0.25,
                "urgency_score": 0.60,
                "resource_score": 0.65,
                "reversibility_score": 0.90,
                "policy_score": 0.95,
                "expected_outcomes": ["Higher confidence classification", "Improved track quality"],
                "rationale": ["Reduces uncertainty before consequential action"],
            },
            {
                "name": "Escalate for human operational review",
                "description": "Present the situation, evidence, uncertainty, and recommended next steps to an authorized human operator.",
                "risk_score": 0.15,
                "urgency_score": 0.80,
                "resource_score": 0.80,
                "reversibility_score": 1.0,
                "policy_score": 1.0,
                "expected_outcomes": ["Timely command awareness", "Human-authorized follow-on action"],
                "rationale": ["Maintains human authority for consequential decisions"],
            },
        ],
    },
    "wildfire-emergency": {
        "name": "Wildfire & Emergency Management",
        "domains": ["wildfire", "emergency", "evacuation", "public-safety"],
        "description": "Wildfire, disaster, evacuation, and multi-agency emergency decision support.",
        "weights": {
            "confidence": 0.20,
            "risk": 0.25,
            "urgency": 0.30,
            "resource": 0.10,
            "reversibility": 0.05,
            "policy": 0.10,
        },
        "default_options": [
            {
                "name": "Continue monitoring and update forecast",
                "description": "Maintain surveillance and refresh weather, spread, infrastructure, and population exposure inputs.",
                "risk_score": 0.35,
                "urgency_score": 0.45,
                "resource_score": 0.90,
                "reversibility_score": 0.95,
                "policy_score": 1.0,
                "expected_outcomes": ["Updated risk picture", "Improved forecast confidence"],
                "rationale": ["Appropriate when current exposure remains manageable"],
            },
            {
                "name": "Pre-stage response resources",
                "description": "Recommend pre-positioning approved response resources closer to the anticipated impact area.",
                "risk_score": 0.20,
                "urgency_score": 0.75,
                "resource_score": 0.55,
                "reversibility_score": 0.80,
                "policy_score": 0.95,
                "expected_outcomes": ["Reduced response time", "Higher readiness"],
                "rationale": ["Balances urgency and reversibility"],
            },
            {
                "name": "Escalate evacuation readiness",
                "description": "Recommend authorized officials review evacuation alerts, routing, vulnerable populations, and transportation capacity.",
                "risk_score": 0.15,
                "urgency_score": 0.90,
                "resource_score": 0.65,
                "reversibility_score": 0.75,
                "policy_score": 1.0,
                "expected_outcomes": ["Faster public warning if needed", "Improved evacuation preparedness"],
                "rationale": ["Keeps evacuation authority with responsible officials"],
            },
        ],
    },
    "critical-infrastructure": {
        "name": "Critical Infrastructure",
        "domains": ["infrastructure", "industrial", "utilities", "cyber-physical"],
        "description": "Resilience and continuity support for utilities, industrial systems, transport, and other critical infrastructure.",
        "weights": {
            "confidence": 0.25,
            "risk": 0.25,
            "urgency": 0.20,
            "resource": 0.15,
            "reversibility": 0.10,
            "policy": 0.05,
        },
        "default_options": [
            {
                "name": "Increase monitoring",
                "description": "Increase telemetry, diagnostics, and corroborating checks around the affected asset or system.",
                "risk_score": 0.25,
                "urgency_score": 0.40,
                "resource_score": 0.90,
                "reversibility_score": 0.95,
                "policy_score": 1.0,
                "expected_outcomes": ["Improved diagnosis", "Reduced uncertainty"],
                "rationale": ["Low-disruption first response"],
            },
            {
                "name": "Prepare controlled mitigation",
                "description": "Recommend authorized operators prepare a reversible mitigation, failover, isolation, or maintenance action.",
                "risk_score": 0.20,
                "urgency_score": 0.70,
                "resource_score": 0.60,
                "reversibility_score": 0.80,
                "policy_score": 0.95,
                "expected_outcomes": ["Reduced outage risk", "Improved resilience"],
                "rationale": ["Prioritizes reversible mitigations before disruptive intervention"],
            },
            {
                "name": "Escalate incident response",
                "description": "Present the anomaly and recommended mitigations to the designated incident authority for approval.",
                "risk_score": 0.15,
                "urgency_score": 0.85,
                "resource_score": 0.75,
                "reversibility_score": 1.0,
                "policy_score": 1.0,
                "expected_outcomes": ["Faster incident coordination", "Authorized intervention"],
                "rationale": ["Maintains human oversight over consequential system changes"],
            },
        ],
    },
}


def get_mission_pack(pack_id: str) -> Dict[str, Any]:
    return MISSION_PACKS.get(pack_id, MISSION_PACKS["critical-infrastructure"])


def select_mission_pack(observation: Dict[str, Any]) -> str:
    text = " ".join(
        str(observation.get(key) or "")
        for key in ("object_type", "source_type", "source_system", "classification_tag")
    ).lower()

    if any(term in text for term in ("vessel", "ais", "maritime", "ship", "arctic", "sar", "distress")):
        return "canada-maritime-arctic"
    if any(term in text for term in ("fire", "smoke", "wildfire", "evac", "flood", "earthquake")):
        return "wildfire-emergency"
    return "critical-infrastructure"


def build_candidate_options(pack_id: str, observation: Dict[str, Any], trigger: Dict[str, Any]) -> List[Dict[str, Any]]:
    pack = get_mission_pack(pack_id)
    confidence = float(observation.get("confidence") or 0.5)
    severity = trigger.get("severity", "low")
    urgency_boost = {"low": 0.0, "medium": 0.10, "high": 0.20}.get(severity, 0.0)

    options: List[Dict[str, Any]] = []
    for template in pack["default_options"]:
        option = dict(template)
        option["confidence"] = confidence
        option["urgency_score"] = min(1.0, float(option.get("urgency_score", 0.5)) + urgency_boost)
        option["assumptions"] = [
            "Input data and provenance are materially accurate",
            "A human operator retains authorization for consequential actions",
        ]
        option["constraints"] = [
            "Respect mission policy, jurisdiction, and information-handling rules",
            "Do not execute consequential action without explicit authorization",
        ]
        option["metadata"] = {"mission_pack": pack_id, "trigger_reasons": trigger.get("reasons", [])}
        options.append(option)
    return options
