from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from app.db.fusion import create_fusion_output_with_provenance
from app.db.observations import insert_observation
from app.db.tracking import associate_observation_to_entity
from app.models.db import engine as decision_engine_db
from app.services.decision_trigger import evaluate_decision_trigger
from app.services.decision_workflow import create_decision_proposal_from_observation


async def process_observation(db: AsyncSession, observation_data: Dict[str, Any]) -> Dict[str, Any]:
    """Run a normalized observation through the complete SitRep decision pipeline.

    The pipeline persists the observation, performs entity association and fusion,
    evaluates whether a decision is warranted, and creates a proposal when needed.
    It never approves or executes a consequential action.
    """
    obs_id = await insert_observation(db, observation_data)

    tracking_result = await associate_observation_to_entity(
        db=db,
        observation_id=obs_id,
        observation=observation_data,
    )

    fusion_result = await create_fusion_output_with_provenance(
        db=db,
        entity_id=tracking_result["entity_id"],
        observation_id=obs_id,
        association=tracking_result["association"],
        association_score=tracking_result["association_score"],
        object_type=observation_data.get("object_type") or "unknown",
        source_system=observation_data.get("source_system"),
        source_type=observation_data.get("source_type"),
        confidence=observation_data.get("confidence") or 0.5,
        classification_tag=observation_data.get("classification_tag") or "UNCLASSIFIED",
        gate_result=tracking_result.get("gate_result"),
        tenant_id=observation_data.get("tenant_id") or "default",
    )

    decision_trigger = evaluate_decision_trigger(
        observation=observation_data,
        tracking=tracking_result,
        fusion=fusion_result,
    )

    decision_proposal = None
    if decision_trigger.get("should_trigger"):
        with Session(decision_engine_db) as decision_session:
            decision_proposal = create_decision_proposal_from_observation(
                session=decision_session,
                observation=observation_data,
                tracking=tracking_result,
                fusion=fusion_result,
                trigger=decision_trigger,
                mission_id=observation_data.get("mission_id"),
            )

    return {
        "status": "ok",
        "observation_id": obs_id,
        **tracking_result,
        **fusion_result,
        "decision_trigger": decision_trigger,
        "decision_proposal": decision_proposal,
    }
