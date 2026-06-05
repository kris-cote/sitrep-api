from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


POLICY_ID = "sitrep_fce_policy_v1"
POLICY_VERSION = "0.1.0"

CLASSIFICATION_ORDER = {
    "UNCLASSIFIED": 0,
    "PROTECTED_A": 1,
    "PROTECTED_B": 2,
    "PROTECTED_C": 3,
    "SECRET": 4,
    "TOP_SECRET": 5,
}

DOMAIN_LEVELS = {
    "open_network": 0,
    "operator_console": 0,
    "protected_a_network": 1,
    "protected_b_network": 2,
    "mission_network": 3,
    "coalition_network": 3,
    "classified_network": 4,
}


@dataclass
class ComplianceDecision:
    policy_id: str
    policy_version: str
    rule_id: str
    source_system: str
    source_type: str
    classification_in: str
    classification_out: str
    security_domain_in: str
    requested_output_domain: str
    enforcement_action: str
    compliance_disposition: str
    reason: str
    human_readable_decision: str
    machine_readable_policy: Dict[str, Any]
    evidence: Dict[str, Any]


def get_active_policy() -> Dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "prototype_mode": True,
        "description": (
            "Prototype machine-readable policy for SitRep-FCE. "
            "Models classification, security-domain, release, redaction, "
            "segregation, and review-required decisions for multi-sensor fusion."
        ),
        "classification_levels": list(CLASSIFICATION_ORDER.keys()),
        "security_domains": list(DOMAIN_LEVELS.keys()),
        "enforcement_actions": [
            "permit",
            "restrict",
            "segregate",
            "redact",
            "review_required",
        ],
        "important_non_claims": [
            "Prototype does not perform real classified downgrade.",
            "Prototype does not replace authorized release authorities.",
            "Prototype models Protected B-style policy conditions using synthetic data.",
            "Operational deployment would require accreditation and integration with approved policy sources.",
        ],
        "rules": [
            {
                "rule_id": "UNCLASSIFIED_TO_OPEN_PERMIT",
                "description": "Unclassified data may be routed to open/operator output.",
                "condition": {
                    "classification_in": "UNCLASSIFIED",
                    "requested_output_domain": ["open_network", "operator_console"],
                },
                "action": "permit",
            },
            {
                "rule_id": "PROTECTED_A_TO_OPEN_REDACT",
                "description": "Protected A data requested for open/operator output requires redaction or restriction.",
                "condition": {
                    "classification_in": "PROTECTED_A",
                    "requested_output_domain": ["open_network", "operator_console"],
                },
                "action": "redact",
            },
            {
                "rule_id": "PROTECTED_B_NO_OPEN_FUSION",
                "description": "Protected B data must not be merged into open-network/operator output without authorized policy conditions.",
                "condition": {
                    "classification_in": "PROTECTED_B",
                    "requested_output_domain": ["open_network", "operator_console"],
                },
                "action": "segregate",
            },
            {
                "rule_id": "SIGINT_PROTECTED_REVIEW_REQUIRED",
                "description": "SIGINT/RF-derived protected observations require additional handling review.",
                "condition": {
                    "source_type": ["sigint", "rf_detection"],
                    "classification_min": "PROTECTED_B",
                },
                "action": "review_required",
            },
            {
                "rule_id": "DOMAIN_DOWNROUTE_RESTRICT",
                "description": "Data cannot be routed from a higher security domain to a lower domain without restriction.",
                "condition": {
                    "security_domain_in_gt_requested_output_domain": True,
                },
                "action": "restrict",
            },
        ],
    }


def _norm(value: Optional[str], default: str) -> str:
    if not value:
        return default
    return value.strip().upper().replace(" ", "_").replace("-", "_")


def _domain_norm(value: Optional[str], default: str) -> str:
    if not value:
        return default
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def evaluate_compliance(
    *,
    source_system: str,
    source_type: str,
    classification_in: str = "UNCLASSIFIED",
    security_domain_in: str = "open_network",
    requested_output_domain: str = "operator_console",
    output_audience: str = "operator_console",
    metadata: Optional[Dict[str, Any]] = None,
) -> ComplianceDecision:
    metadata = metadata or {}

    source_type_normalized = _domain_norm(source_type, "unknown")
    classification = _norm(classification_in, "UNCLASSIFIED")
    security_domain = _domain_norm(security_domain_in, "open_network")
    requested_domain = _domain_norm(requested_output_domain, "operator_console")

    class_level = CLASSIFICATION_ORDER.get(classification, 0)
    domain_level = DOMAIN_LEVELS.get(security_domain, 0)
    requested_level = DOMAIN_LEVELS.get(requested_domain, 0)

    policy = get_active_policy()

    rule_id = "UNCLASSIFIED_TO_OPEN_PERMIT"
    action = "permit"
    disposition = "compliant"
    classification_out = classification
    reason = "Policy permits routing to requested output domain."

    if domain_level > requested_level:
        rule_id = "DOMAIN_DOWNROUTE_RESTRICT"
        action = "restrict"
        disposition = "restricted"
        reason = (
            f"Input security domain {security_domain} exceeds requested output "
            f"domain {requested_domain}; output must be restricted."
        )

    if classification == "PROTECTED_A" and requested_level == 0:
        rule_id = "PROTECTED_A_TO_OPEN_REDACT"
        action = "redact"
        disposition = "allowed_with_redaction"
        classification_out = "UNCLASSIFIED"
        reason = (
            "Protected A observation requested for operator/open output; "
            "sensitive fields must be redacted before fusion output exposure."
        )

    if classification == "PROTECTED_B" and requested_level == 0:
        rule_id = "PROTECTED_B_NO_OPEN_FUSION"
        action = "segregate"
        disposition = "segregated"
        classification_out = "PROTECTED_B"
        reason = (
            "Protected B observation cannot be merged into open/operator output "
            "under prototype policy; observation is segregated from open fusion output."
        )

    if source_type_normalized in {"sigint", "rf_detection"} and class_level >= CLASSIFICATION_ORDER["PROTECTED_B"]:
        rule_id = "SIGINT_PROTECTED_REVIEW_REQUIRED"
        action = "review_required"
        disposition = "restricted_review_required"
        classification_out = classification
        reason = (
            "Protected SIGINT/RF-derived observation requires additional handling review "
            "before release or cross-domain fusion."
        )

    human = (
        f"{action.upper()}: {source_system} / {source_type_normalized} "
        f"({classification}, {security_domain}) to {requested_domain}. {reason}"
    )

    return ComplianceDecision(
        policy_id=POLICY_ID,
        policy_version=POLICY_VERSION,
        rule_id=rule_id,
        source_system=source_system,
        source_type=source_type_normalized,
        classification_in=classification,
        classification_out=classification_out,
        security_domain_in=security_domain,
        requested_output_domain=requested_domain,
        enforcement_action=action,
        compliance_disposition=disposition,
        reason=reason,
        human_readable_decision=human,
        machine_readable_policy=policy,
        evidence={
            "output_audience": output_audience,
            "classification_level": class_level,
            "security_domain_level": domain_level,
            "requested_domain_level": requested_level,
            "metadata": metadata,
        },
    )


def decision_to_dict(decision: ComplianceDecision) -> Dict[str, Any]:
    return asdict(decision)
