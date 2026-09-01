from __future__ import annotations

from typing import Any, Dict, Optional

from sqlmodel import Session

from app.models.decision import CourseOfAction, DecisionAudit, DecisionRecord
from app.services.decision_engine import policy_flags, rank_courses_of_action, risk_label
from app.services.mission_packs import build_candidate_options, get_mission_pack, select_mission_pack


def create_decision_proposal_from_observation(
    session: Session,
    observation: Dict[str, Any],
    tracking: Dict[str, Any],
    fusion: Dict[str, Any],
    trigger: Dict[str, Any],
    mission_id: Optional[str] = None,
    correlated_situation: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Create a proposed decision when an explainable trigger fires.

    This never approves or executes an action. It only creates a ranked proposal
    with evidence and provenance for later human review.
    """
    if not trigger.get("should_trigger"):
        return None

    pack_id = select_mission_pack(observation)
    pack = get_mission_pack(pack_id)
    options = build_candidate_options(pack_id, observation, trigger)

    if correlated_situation:
        situation_risk = float(correlated_situation.get("risk_score") or 0.0)
        situation_urgency = float(correlated_situation.get("urgency_score") or 0.0)
        for option in options:
            option["risk_score"] = max(float(option.get("risk_score", 0.0)), situation_risk)
            option["urgency_score"] = max(float(option.get("urgency_score", 0.0)), situation_urgency)
            option.setdefault("metadata", {})["correlated_situation"] = correlated_situation

    ranked = rank_courses_of_action(options, pack.get("weights"))
    flags = policy_flags(ranked)

    situation_id = str(
        (correlated_situation or {}).get("situation_id")
        or fusion.get("fusion_output_id")
        or fusion.get("id")
        or tracking.get("entity_id")
        or observation.get("id")
        or "unknown-situation"
    )

    evidence = [
        {
            "type": "observation",
            "source_system": observation.get("source_system"),
            "source_type": observation.get("source_type"),
            "confidence": observation.get("confidence"),
            "object_type": observation.get("object_type"),
            "classification_tag": observation.get("classification_tag"),
        },
        {
            "type": "tracking",
            "entity_id": tracking.get("entity_id"),
            "association": tracking.get("association"),
            "association_score": tracking.get("association_score"),
            "gate_result": tracking.get("gate_result"),
        },
        {
            "type": "fusion",
            "fusion_output_id": fusion.get("fusion_output_id") or fusion.get("id"),
            "requires_attention": fusion.get("requires_attention"),
            "alert": fusion.get("alert"),
            "anomaly": fusion.get("anomaly"),
        },
    ]
    if correlated_situation:
        evidence.append({"type": "correlated_situation", **correlated_situation})

    decision = DecisionRecord(
        mission_id=mission_id,
        situation_id=situation_id,
        domain=pack_id,
        title=f"Decision review: {observation.get('object_type') or 'operational anomaly'}",
        summary="; ".join(trigger.get("reasons", [])),
        confidence=max(ranked[0].confidence, float((correlated_situation or {}).get("confidence") or 0.0)),
        risk_level=risk_label(ranked),
        policy_flags=flags,
        evidence=evidence,
        context={
            "mission_pack": pack_id,
            "mission_pack_name": pack.get("name"),
            "trigger": trigger,
            "entity_id": tracking.get("entity_id"),
            "correlated_situation": correlated_situation,
        },
    )
    session.add(decision)
    session.flush()

    records = []
    for index, item in enumerate(ranked, start=1):
        record = CourseOfAction(
            decision_id=decision.id,
            name=item.name,
            description=item.description,
            rank=index,
            score=item.score,
            confidence=item.confidence,
            risk_score=item.risk_score,
            urgency_score=item.urgency_score,
            resource_score=item.resource_score,
            reversibility_score=item.reversibility_score,
            policy_score=item.policy_score,
            expected_outcomes=item.expected_outcomes,
            assumptions=item.assumptions,
            constraints=item.constraints,
            rationale=item.rationale,
            metadata_json=item.metadata,
        )
        session.add(record)
        records.append(record)

    session.flush()
    decision.recommended_option_id = records[0].id
    session.add(
        DecisionAudit(
            decision_id=decision.id,
            action="generated_from_observation",
            actor="sitrep-decision-workflow",
            payload={
                "mission_pack": pack_id,
                "recommended_option_id": records[0].id,
                "trigger_reasons": trigger.get("reasons", []),
                "policy_flags": flags,
                "correlated_situation_id": (correlated_situation or {}).get("situation_id"),
            },
        )
    )
    session.commit()

    return {
        "decision_id": decision.id,
        "situation_id": decision.situation_id,
        "mission_pack": pack_id,
        "mission_pack_name": pack.get("name"),
        "status": decision.status,
        "recommended_option_id": decision.recommended_option_id,
        "recommended_option": records[0].name,
        "confidence": decision.confidence,
        "risk_level": decision.risk_level,
        "requires_human_authorization": decision.requires_human_authorization,
        "policy_flags": decision.policy_flags,
    }
