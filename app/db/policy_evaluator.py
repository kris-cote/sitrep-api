from typing import Dict, Any, List


CLASSIFICATION_ORDER = {
    "UNCLASSIFIED": 0,
    "PROTECTED_A": 1,
    "PROTECTED_B": 2,
    "PROTECTED_C": 3,
    "SECRET": 4,
    "TOP_SECRET": 5,
}


def normalize_classification(value: str | None) -> str:
    if not value:
        return "UNCLASSIFIED"

    cleaned = value.upper().replace(" ", "_").replace("-", "_")

    aliases = {
        "U": "UNCLASSIFIED",
        "UNCLASS": "UNCLASSIFIED",
        "PROTECTED": "PROTECTED_A",
        "PROTECTEDA": "PROTECTED_A",
        "PROTECTEDB": "PROTECTED_B",
        "PROTECTEDC": "PROTECTED_C",
        "TS": "TOP_SECRET",
    }

    return aliases.get(cleaned, cleaned)


def classification_rank(value: str | None) -> int:
    normalized = normalize_classification(value)
    return CLASSIFICATION_ORDER.get(normalized, 0)


def evaluate_policy_context(
    classification_tag: str | None,
    source_system: str | None,
    source_type: str | None,
    output_audience: str = "operator_console",
    prototype_mode: bool = True,
) -> Dict[str, Any]:
    classification_in = normalize_classification(classification_tag)

    redacted_fields: List[str] = []
    handling_caveats: List[str] = []

    # Prototype rule:
    # Keep output classification the same as input unless restricted fields are present.
    classification_out = classification_in

    cross_domain_transfer = False
    release_decision = "allowed"

    policy_reason = (
        "Prototype mode: output classification matches input classification and no restricted "
        "fields are included in operator output."
    )

    if source_type in ["rf_detection", "sigint"]:
        handling_caveats.append(
            "RF/SIGINT-derived observations may require additional handling review in non-prototype deployments."
        )

    if classification_rank(classification_in) >= classification_rank("SECRET"):
        release_decision = "restricted"
        policy_reason = (
            "High-side classification detected. Prototype records lineage but does not perform "
            "cross-domain downgrade or release."
        )

    if output_audience == "public_demo" and classification_rank(classification_in) > 0:
        release_decision = "redacted"
        redacted_fields.extend(["raw_payload", "source_specific_identifiers"])
        classification_out = "UNCLASSIFIED"
        cross_domain_transfer = True
        policy_reason = (
            "Public demo output requested for protected input. Restricted fields would be redacted "
            "and output downgraded in prototype policy mode."
        )

    return {
        "policy_model": "sitrep_policy_evaluator_v1",
        "policy_version": "0.1.0",
        "prototype_mode": prototype_mode,
        "source_system": source_system,
        "source_type": source_type,
        "output_audience": output_audience,
        "classification_in": classification_in,
        "classification_out": classification_out,
        "release_decision": release_decision,
        "cross_domain_transfer": cross_domain_transfer,
        "redacted_fields": redacted_fields,
        "handling_caveats": handling_caveats,
        "policy_reason": policy_reason,
    }
