import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.fusion_model import score_multimodal_fusion_model
from app.db.source_reliability import get_source_trust_weight
from app.db.policy_evaluator import evaluate_policy_context


async def get_entity_observation_ids(db: AsyncSession, entity_id: str):
    query = text("""
        SELECT observation_id
        FROM associations
        WHERE entity_id = :entity_id
        ORDER BY created_at ASC
    """)

    result = await db.execute(query, {"entity_id": entity_id})
    return [str(row[0]) for row in result.fetchall()]


async def create_fusion_output_with_provenance(
    db: AsyncSession,
    entity_id: str,
    observation_id: str,
    association: str,
    association_score: float,
    object_type: str,
    source_system: str,
    source_type: str,
    confidence: float,
    classification_tag: str = "UNCLASSIFIED",
    tenant_id: str = "default",
    gate_result: dict | None = None,
):
    gate_result = gate_result or {}

    source_trust_weight = await get_source_trust_weight(
        db=db,
        source_system=source_system,
        source_type=source_type,
    )

    model_observation = {
        "source_system": source_system,
        "source_type": source_type,
        "object_type": object_type,
        "confidence": confidence,
        "distance_km": gate_result.get("distance_km"),
        "time_delta_seconds": gate_result.get("time_delta_seconds"),
        "estimated_speed_knots": gate_result.get("estimated_speed_knots"),
        "gate_passed": gate_result.get("gate_passed", True),
        "gate_status": gate_result.get("gate_status"),
        "gate_reason": gate_result.get("gate_reason"),
        "object_type_match": 1.0,
    }

    model_output = score_multimodal_fusion_model(
        observation=model_observation,
        association_score=association_score,
        association=association,
        source_trust_weight=source_trust_weight,
    )

    fused_confidence = model_output["final_score"]

    if association == "created_new_entity":
        assessment = f"New probable {object_type or 'unknown object'} track created"
        explanation = (
            f"A new persistent entity was created from {source_type} observation "
            f"provided by {source_system}. No existing active entity met the association threshold."
        )
    else:
        assessment = f"Probable {object_type or 'unknown object'} track maintained"
        explanation = (
            f"Observation from {source_system} ({source_type}) was associated to an existing "
            f"{object_type or 'unknown'} entity with association score {association_score}."
        )

    evidence = [
        {
            "observation_id": observation_id,
            "source_system": source_system,
            "source_type": source_type,
            "input_confidence": confidence,
            "association_score": association_score,
            "association": association,
            "gate_result": gate_result,
            "model_output": model_output,
        }
    ]

    fusion_query = text("""
        INSERT INTO fusion_outputs (
            entity_id,
            assessment,
            confidence,
            explanation,
            evidence,
            tenant_id,
            created_at
        )
        VALUES (
            :entity_id,
            :assessment,
            :confidence,
            :explanation,
            CAST(:evidence AS jsonb),
            :tenant_id,
            clock_timestamp()
        )
        RETURNING id
    """)

    fusion_result = await db.execute(
        fusion_query,
        {
            "entity_id": entity_id,
            "assessment": assessment,
            "confidence": fused_confidence,
            "explanation": explanation,
            "evidence": json.dumps(evidence),
            "tenant_id": tenant_id,
        },
    )

    fusion_id = str(fusion_result.fetchone()[0])

    all_observation_ids = await get_entity_observation_ids(db, entity_id)

    policy_context = evaluate_policy_context(
        classification_tag=classification_tag,
        source_system=source_system,
        source_type=source_type,
        output_audience="operator_console",
        prototype_mode=True,
    )

    processing_steps = [
        {
            "step": "observation_ingest",
            "service": "sitrep-api",
            "version": "local-dev-v1",
        },
        {
            "step": "entity_association",
            "service": "entity-resolver",
            "method": "spatial_type_confidence_scoring",
            "association_score": association_score,
            "gate_result": gate_result,
        },
        {
            "step": "track_update",
            "service": "track-manager",
        },
        {
            "step": "ai_fusion_model_scoring",
            "service": "fusion-model",
            "model_name": model_output["model_name"],
            "model_version": model_output["model_version"],
            "model_type": model_output["model_type"],
            "model_status": model_output["model_status"],
            "source_trust_weight": model_output["source_trust_weight"],
            "baseline_score": model_output["baseline_score"],
            "learned_model_available": model_output.get("learned_model_available"),
            "learned_model_name": model_output.get("learned_model_name"),
            "learned_model_version": model_output.get("learned_model_version"),
            "learned_model_type": model_output.get("learned_model_type"),
            "learned_model_score": model_output.get("learned_model_score"),
            "ai_score": model_output["ai_score"],
            "final_score": model_output["final_score"],
            "uncertainty_score": model_output["uncertainty_score"],
            "uncertainty_level": model_output["uncertainty_level"],
            "confidence_drivers": model_output["confidence_drivers"],
            "uncertainty_drivers": model_output["uncertainty_drivers"],
            "distance_km": model_output.get("distance_km"),
            "time_delta_seconds": model_output.get("time_delta_seconds"),
            "estimated_speed_knots": model_output.get("estimated_speed_knots"),
            "gate_status": model_output.get("gate_status"),
            "gate_reason": model_output.get("gate_reason"),
        },
        {
            "step": "policy_evaluation",
            "service": "policy-evaluator",
            "policy_model": policy_context["policy_model"],
            "policy_version": policy_context["policy_version"],
            "classification_in": policy_context["classification_in"],
            "classification_out": policy_context["classification_out"],
            "release_decision": policy_context["release_decision"],
            "cross_domain_transfer": policy_context["cross_domain_transfer"],
        },
        {
            "step": "fusion_output_created",
            "service": "fusion-explainer",
            "fusion_confidence": fused_confidence,
        },
    ]

    provenance_query = text("""
        INSERT INTO provenance_records (
            output_type,
            output_id,
            derived_from_observations,
            processing_steps,
            policy_context,
            created_at
        )
        VALUES (
            'fusion_output',
            :output_id,
            CAST(:derived_from_observations AS jsonb),
            CAST(:processing_steps AS jsonb),
            CAST(:policy_context AS jsonb),
            clock_timestamp()
        )
        RETURNING id
    """)

    provenance_result = await db.execute(
        provenance_query,
        {
            "output_id": fusion_id,
            "derived_from_observations": json.dumps(all_observation_ids),
            "processing_steps": json.dumps(processing_steps),
            "policy_context": json.dumps(policy_context),
        },
    )

    provenance_id = str(provenance_result.fetchone()[0])

    return {
        "fusion_id": fusion_id,
        "fusion_assessment": assessment,
        "fusion_confidence": fused_confidence,
        "fusion_explanation": explanation,
        "model_output": model_output,
        "policy_context": policy_context,
        "provenance_id": provenance_id,
    }
