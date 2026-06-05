from datetime import datetime, timezone, timedelta
import json
from sqlalchemy import text
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.spatiotemporal import evaluate_spatiotemporal_gate
from app.dependencies import get_db
from app.db.observations import insert_observation
from app.db.tracking import associate_observation_to_entity
from app.db.fusion import create_fusion_output_with_provenance
from app.db.operator_actions import create_operator_action_for_entity
from app.services.compliance_engine import evaluate_compliance, decision_to_dict


router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


async def process_demo_observation(db: AsyncSession, observation_data: dict):
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
        tenant_id=observation_data.get("tenant_id") or "default",
        gate_result=tracking_result.get("gate_result"),
    )
    return {
        "observation_id": obs_id,
        **tracking_result,
        **fusion_result,
    }


@router.post("/vessel-track")
async def create_demo_vessel_track(
    confirm: bool = True,
    tenant_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    base_time = datetime(2026, 4, 24, 18, 30, tzinfo=timezone.utc)

    observations = [
        {
            "source_system": "radar_sim",
            "source_type": "radar",
            "object_type": "vessel",
            "collected_at": base_time,
            "latitude": 49.165,
            "longitude": -123.936,
            "altitude_m": None,
            "confidence": 0.82,
            "features": {
                "speed_knots": 18,
                "heading_degrees": 135,
                "sensor_range_nm": 4.2,
            },
            "raw_payload": {
                "external_id": "RADAR-DEMO-001",
                "range_nm": 4.2,
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "operator_report_sim",
            "source_type": "text_report",
            "object_type": "vessel",
            "collected_at": base_time + timedelta(minutes=2, seconds=30),
            "latitude": 49.168,
            "longitude": -123.931,
            "altitude_m": None,
            "confidence": 0.72,
            "features": {
                "report_text": "Operator reports unknown small vessel moving southeast near previous RF contact.",
                "extracted_heading": 140,
                "extracted_activity": "moving southeast",
                "text_entities": ["unknown vessel", "southeast", "RF contact"],
            },
            "raw_payload": {
                "external_id": "TEXT-DEMO-001",
                "report_channel": "operator_chat",
                "report_text": "Unknown small vessel observed moving southeast near previous RF contact.",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "camera_sim",
            "source_type": "eo_video",
            "object_type": "vessel",
            "collected_at": base_time + timedelta(minutes=1),
            "latitude": 49.166,
            "longitude": -123.934,
            "altitude_m": None,
            "confidence": 0.88,
            "features": {
                "speed_knots": 19,
                "heading_degrees": 137,
                "visual_class": "small_vessel",
            },
            "raw_payload": {
                "external_id": "CAM-DEMO-001",
                "frame_id": "frame_demo_8821",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "rf_sim",
            "source_type": "rf_detection",
            "object_type": "vessel",
            "collected_at": base_time + timedelta(minutes=2),
            "latitude": 49.167,
            "longitude": -123.932,
            "altitude_m": None,
            "confidence": 0.79,
            "features": {
                "signal_type": "marine_radio",
                "speed_knots": 20,
                "heading_degrees": 139,
            },
            "raw_payload": {
                "external_id": "RF-DEMO-001",
                "frequency_mhz": 156.8,
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
    ]

    results = []

    for observation in observations:
        result = await process_demo_observation(db, observation)
        results.append(result)

    entity_id = results[-1]["entity_id"]
    track_id = results[-1]["track_id"]

    operator_action_id = None

    if confirm:
        operator_action_id = await create_operator_action_for_entity(
            db=db,
            entity_id=entity_id,
            action_type="confirm",
            action_note="Demo operator confirms persistent vessel track based on radar, EO video, and RF lineage.",
            operator_id="demo_operator",
            identity_label="unknown vessel - demo confirmed track",
        )

    return {
        "status": "ok",
        "scenario": "multi_modal_vessel_track",
        "tenant_id": tenant_id,
        "entity_id": entity_id,
        "track_id": track_id,
        "observation_count": len(results),
        "observations": results,
        "operator_action_id": operator_action_id,
        "next_urls": {
            "cop": f"/api/v1/cop/?tenant_id={tenant_id}",
            "track": f"/api/v1/entities/{entity_id}/track",
            "lineage": f"/api/v1/entities/{entity_id}/lineage",
            "operator_actions": f"/api/v1/entities/{entity_id}/operator-actions",
        },
    }
@router.post("/reset")
async def reset_demo_tenant(
    tenant_id: str = "proposal_demo_001",
    db: AsyncSession = Depends(get_db),
):
    """
    Reset demo data for a tenant.

    This is intended for synthetic/demo tenants only.
    It removes operational objects, observations, tracks, fusion outputs,
    provenance records, and operator actions associated with the tenant.
    """

    # Find entities and observations for the tenant first.
    entity_result = await db.execute(
        text("""
            SELECT id
            FROM entities
            WHERE tenant_id = :tenant_id
        """),
        {"tenant_id": tenant_id},
    )

    entity_ids = [str(row[0]) for row in entity_result.fetchall()]

    observation_result = await db.execute(
        text("""
            SELECT id
            FROM observations
            WHERE tenant_id = :tenant_id
        """),
        {"tenant_id": tenant_id},
    )

    observation_ids = [str(row[0]) for row in observation_result.fetchall()]

    # Delete records in dependency-safe order.
    if entity_ids:
        await db.execute(
            text("""
                DELETE FROM operator_actions
                WHERE entity_id::text = ANY(:entity_ids)
            """),
            {"entity_ids": entity_ids},
        )

        await db.execute(
            text("""
                DELETE FROM provenance_records
                WHERE output_id IN (
                    SELECT id FROM fusion_outputs
                    WHERE entity_id::text = ANY(:entity_ids)
                )
            """),
            {"entity_ids": entity_ids},
        )

        await db.execute(
            text("""
                DELETE FROM fusion_outputs
                WHERE entity_id::text = ANY(:entity_ids)
            """),
            {"entity_ids": entity_ids},
        )

        await db.execute(
            text("""
                DELETE FROM associations
                WHERE entity_id::text = ANY(:entity_ids)
            """),
            {"entity_ids": entity_ids},
        )

        await db.execute(
            text("""
                DELETE FROM track_points
                WHERE track_id IN (
                    SELECT id FROM tracks
                    WHERE entity_id::text = ANY(:entity_ids)
                )
            """),
            {"entity_ids": entity_ids},
        )

        await db.execute(
            text("""
                DELETE FROM tracks
                WHERE entity_id::text = ANY(:entity_ids)
            """),
            {"entity_ids": entity_ids},
        )

        await db.execute(
            text("""
                DELETE FROM entities
                WHERE id::text = ANY(:entity_ids)
            """),
            {"entity_ids": entity_ids},
        )

    if observation_ids:
        await db.execute(
            text("""
                DELETE FROM observations
                WHERE id::text = ANY(:observation_ids)
            """),
            {"observation_ids": observation_ids},
        )

    return {
        "status": "ok",
        "tenant_id": tenant_id,
        "deleted_entity_count": len(entity_ids),
        "deleted_observation_count": len(observation_ids),
    }
@router.post("/adversarial-track")
async def create_adversarial_track_demo(
    tenant_id: str = "adversarial_demo",
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a normal multi-modal vessel track, then injects an impossible
    far-away observation that should not be merged into the original entity.
    """

    base_time = datetime(2026, 4, 24, 18, 30, tzinfo=timezone.utc)

    normal_observations = [
        {
            "source_system": "radar_sim",
            "source_type": "radar",
            "object_type": "vessel",
            "collected_at": base_time,
            "latitude": 49.165,
            "longitude": -123.936,
            "altitude_m": None,
            "confidence": 0.82,
            "features": {
                "speed_knots": 18,
                "heading_degrees": 135,
                "sensor_range_nm": 4.2,
            },
            "raw_payload": {
                "external_id": "RADAR-ADV-001",
                "range_nm": 4.2,
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "camera_sim",
            "source_type": "eo_video",
            "object_type": "vessel",
            "collected_at": base_time + timedelta(minutes=1),
            "latitude": 49.166,
            "longitude": -123.934,
            "altitude_m": None,
            "confidence": 0.88,
            "features": {
                "speed_knots": 19,
                "heading_degrees": 137,
                "visual_class": "small_vessel",
            },
            "raw_payload": {
                "external_id": "CAM-ADV-001",
                "frame_id": "frame_adv_8821",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "rf_sim",
            "source_type": "rf_detection",
            "object_type": "vessel",
            "collected_at": base_time + timedelta(minutes=2),
            "latitude": 49.167,
            "longitude": -123.932,
            "altitude_m": None,
            "confidence": 0.79,
            "features": {
                "signal_type": "marine_radio",
                "speed_knots": 20,
                "heading_degrees": 139,
            },
            "raw_payload": {
                "external_id": "RF-ADV-001",
                "frequency_mhz": 156.8,
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
    ]

    normal_results = []

    for observation in normal_observations:
        result = await process_demo_observation(db, observation)
        normal_results.append(result)

    original_entity_id = normal_results[-1]["entity_id"]
    original_track_id = normal_results[-1]["track_id"]

    far_observation = {
        "source_system": "radar_sim_far",
        "source_type": "radar",
        "object_type": "vessel",
        "collected_at": base_time + timedelta(minutes=3),
        "latitude": 50.500,
        "longitude": -126.000,
        "altitude_m": None,
        "confidence": 0.91,
        "features": {
            "speed_knots": 18,
            "heading_degrees": 140,
            "adversarial_case": "impossible_movement",
        },
        "raw_payload": {
            "external_id": "RADAR-FAR-ADV-001",
            "note": "Adversarial impossible movement test",
        },
        "classification_tag": "UNCLASSIFIED",
        "tenant_id": tenant_id,
    }

    # Build explicit rejected-candidate evidence before processing the far observation.
    # This shows that the original vessel track was considered and rejected
    # because the movement would be physically impossible.
    original_candidate_entity = {
        "id": original_entity_id,
        "entity_type": "vessel",
        "current_latitude": normal_observations[-1]["latitude"],
        "current_longitude": normal_observations[-1]["longitude"],
        "last_seen_at": normal_observations[-1]["collected_at"],
        "current_confidence": normal_results[-1].get("fusion_confidence") or 0.895,
    }

    rejected_candidate_gate = evaluate_spatiotemporal_gate(
        observation=far_observation,
        entity=original_candidate_entity,
    )

    far_result = await process_demo_observation(db, far_observation)

    far_entity_id = far_result["entity_id"]
    rejected_merge = original_entity_id != far_entity_id

    rejected_candidate_evidence = {
        "candidate_entity_id": original_entity_id,
        "candidate_track_id": original_track_id,
        "candidate_last_known_latitude": original_candidate_entity["current_latitude"],
        "candidate_last_known_longitude": original_candidate_entity["current_longitude"],
        "candidate_last_seen_at": str(original_candidate_entity["last_seen_at"]),
        "incoming_observation_source": far_observation["source_system"],
        "incoming_observation_type": far_observation["source_type"],
        "incoming_observation_latitude": far_observation["latitude"],
        "incoming_observation_longitude": far_observation["longitude"],
        "incoming_observation_time": str(far_observation["collected_at"]),
        "gate_result": rejected_candidate_gate,
        "rejection_decision": "do_not_merge_existing_track" if not rejected_candidate_gate.get("gate_passed") else "gate_passed",
        "resulting_action": "created_separate_entity" if rejected_merge else "merged_with_existing_entity",
    }

    return {
        "status": "ok",
        "scenario": "adversarial_impossible_movement",
        "tenant_id": tenant_id,
        "expected_behavior": (
            "far observation should create a separate entity, not merge into the original vessel track"
        ),
        "passed": rejected_merge,
        "rejected_candidate_evidence": rejected_candidate_evidence,
        "original_entity_id": original_entity_id,
        "original_track_id": original_track_id,
        "far_observation_entity_id": far_entity_id,
        "far_observation_result": far_result,
        "entity_count_expected": 2,
        "normal_observation_count": len(normal_results),
        "next_urls": {
            "cop": f"/api/v1/cop/?tenant_id={tenant_id}",
            "original_track": f"/api/v1/entities/{original_entity_id}/track",
            "far_track": f"/api/v1/entities/{far_entity_id}/track",
        },
    }
@router.post("/arctic-isr")
async def create_arctic_isr_demo(
    tenant_id: str = "arctic_demo",
    confirm: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """
    Synthetic Arctic ISR scenario.

    Fuses satellite cue, RF detection, telemetry, and operator text report
    into a persistent Arctic maritime vessel track.
    """

    base_time = datetime(2026, 4, 24, 18, 30, tzinfo=timezone.utc)

    observations = [
        {
            "source_system": "satellite_sim",
            "source_type": "satellite",
            "object_type": "vessel",
            "collected_at": base_time,
            "latitude": 69.650,
            "longitude": -133.900,
            "altitude_m": None,
            "confidence": 0.76,
            "features": {
                "sensor": "synthetic_sar",
                "ice_edge_distance_km": 12.4,
                "detected_shape": "elongated_surface_contact",
                "cloud_cover_percent": 65,
            },
            "raw_payload": {
                "external_id": "SAT-ARCTIC-001",
                "collection_mode": "synthetic_sar_cue",
                "note": "Satellite-derived maritime contact candidate near Arctic operating area.",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "rf_sim",
            "source_type": "rf_detection",
            "object_type": "vessel",
            "collected_at": base_time + timedelta(minutes=2),
            "latitude": 69.652,
            "longitude": -133.895,
            "altitude_m": None,
            "confidence": 0.81,
            "features": {
                "signal_type": "marine_radio",
                "frequency_mhz": 156.8,
                "bearing_degrees": 92,
                "signal_strength_dbm": -72,
            },
            "raw_payload": {
                "external_id": "RF-ARCTIC-001",
                "frequency_mhz": 156.8,
                "note": "RF activity detected near satellite contact.",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "telemetry_sim",
            "source_type": "telemetry",
            "object_type": "vessel",
            "collected_at": base_time + timedelta(minutes=3),
            "latitude": 69.653,
            "longitude": -133.890,
            "altitude_m": None,
            "confidence": 0.84,
            "features": {
                "speed_knots": 12,
                "heading_degrees": 80,
                "platform_status": "unknown_contact",
                "track_quality": "medium",
            },
            "raw_payload": {
                "external_id": "TEL-ARCTIC-001",
                "note": "Synthetic telemetry-like update associated with Arctic contact.",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "operator_report_sim",
            "source_type": "text_report",
            "object_type": "vessel",
            "collected_at": base_time + timedelta(minutes=4),
            "latitude": 69.654,
            "longitude": -133.886,
            "altitude_m": None,
            "confidence": 0.73,
            "features": {
                "report_text": "Operator report: unknown vessel-sized contact moving east along ice edge near RF cue.",
                "text_entities": ["unknown vessel", "ice edge", "RF cue", "moving east"],
                "extracted_heading": 85,
                "extracted_activity": "moving east along ice edge",
            },
            "raw_payload": {
                "external_id": "TEXT-ARCTIC-001",
                "report_channel": "operator_chat",
                "report_text": "Unknown vessel-sized contact moving east along ice edge near RF cue.",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
    ]

    results = []

    for observation in observations:
        result = await process_demo_observation(db, observation)
        results.append(result)

    entity_id = results[-1]["entity_id"]
    track_id = results[-1]["track_id"]

    operator_action_id = None

    return {
        "status": "ok",
        "scenario": "arctic_isr_fusion",
        "tenant_id": tenant_id,
        "description": (
            "Synthetic Arctic ISR scenario fusing satellite cue, RF detection, telemetry, "
            "and operator text report into a persistent maritime track."
        ),
        "entity_id": entity_id,
        "track_id": track_id,
        "observation_count": len(results),
        "observations": results,
        "operator_action_id": operator_action_id,
        "next_urls": {
            "cop": f"/api/v1/cop/?tenant_id={tenant_id}",
            "track": f"/api/v1/entities/{entity_id}/track",
            "lineage": f"/api/v1/entities/{entity_id}/lineage",
            "operator_actions": f"/api/v1/entities/{entity_id}/operator-actions",
        },
    }
@router.post("/airborne-track")
async def create_airborne_track_demo(
    tenant_id: str = "airborne_demo",
    confirm: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """
    Synthetic airborne multi-sensor scenario.

    Fuses radar, EO/IR, telemetry, and operator text report into a persistent
    aircraft track.
    """

    base_time = datetime(2026, 4, 24, 18, 30, tzinfo=timezone.utc)

    observations = [
        {
            "source_system": "radar_sim",
            "source_type": "radar",
            "object_type": "aircraft",
            "collected_at": base_time,
            "latitude": 64.8250,
            "longitude": -147.7200,
            "altitude_m": 7600,
            "confidence": 0.86,
            "features": {
                "speed_knots": 410,
                "heading_degrees": 92,
                "radar_cross_section": "low_observable_candidate",
                "sensor_range_nm": 86,
            },
            "raw_payload": {
                "external_id": "RADAR-AIR-001",
                "range_nm": 86,
                "note": "Radar contact detected in northern airspace corridor.",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "eo_ir_sim",
            "source_type": "eo_ir",
            "object_type": "aircraft",
            "collected_at": base_time + timedelta(seconds=90),
            "latitude": 64.8260,
            "longitude": -147.6900,
            "altitude_m": 7625,
            "confidence": 0.82,
            "features": {
                "thermal_signature": "airborne_hotspot",
                "visual_class": "fixed_wing_candidate",
                "heading_degrees": 93,
                "speed_knots": 415,
                "cloud_obscuration_percent": 35,
            },
            "raw_payload": {
                "external_id": "EOIR-AIR-001",
                "frame_id": "eo_ir_frame_4471",
                "note": "EO/IR cue consistent with airborne object near radar track.",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "telemetry_sim",
            "source_type": "telemetry",
            "object_type": "aircraft",
            "collected_at": base_time + timedelta(seconds=180),
            "latitude": 64.8270,
            "longitude": -147.6600,
            "altitude_m": 7650,
            "confidence": 0.80,
            "features": {
                "speed_knots": 420,
                "heading_degrees": 94,
                "track_quality": "medium",
                "altitude_rate_mps": 0.4,
                "source_note": "synthetic telemetry-like correlation",
            },
            "raw_payload": {
                "external_id": "TEL-AIR-001",
                "note": "Telemetry-like update correlated with radar and EO/IR track.",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
        {
            "source_system": "operator_report_sim",
            "source_type": "text_report",
            "object_type": "aircraft",
            "collected_at": base_time + timedelta(seconds=270),
            "latitude": 64.8280,
            "longitude": -147.6300,
            "altitude_m": 7660,
            "confidence": 0.74,
            "features": {
                "report_text": "Operator report: unknown aircraft contact continuing eastbound, correlated with radar and EO/IR cues.",
                "text_entities": [
                    "unknown aircraft",
                    "eastbound",
                    "radar cue",
                    "EO/IR cue",
                ],
                "extracted_heading": 94,
                "extracted_activity": "continuing eastbound",
            },
            "raw_payload": {
                "external_id": "TEXT-AIR-001",
                "report_channel": "operator_chat",
                "report_text": "Unknown aircraft contact continuing eastbound, correlated with radar and EO/IR cues.",
            },
            "classification_tag": "UNCLASSIFIED",
            "tenant_id": tenant_id,
        },
    ]

    results = []

    for observation in observations:
        result = await process_demo_observation(db, observation)
        results.append(result)

    entity_id = results[-1]["entity_id"]
    track_id = results[-1]["track_id"]

    operator_action_id = None

    return {
        "status": "ok",
        "scenario": "airborne_multi_sensor_track",
        "tenant_id": tenant_id,
        "description": (
            "Synthetic airborne multi-sensor scenario fusing radar, EO/IR, telemetry, "
            "and operator text report into a persistent aircraft track."
        ),
        "entity_id": entity_id,
        "track_id": track_id,
        "observation_count": len(results),
        "observations": results,
        "operator_action_id": operator_action_id,
        "next_urls": {
            "cop": f"/api/v1/cop/?tenant_id={tenant_id}",
            "track": f"/api/v1/entities/{entity_id}/track",
            "lineage": f"/api/v1/entities/{entity_id}/lineage",
            "operator_actions": f"/api/v1/entities/{entity_id}/operator-actions",
        },
    }

@router.post("/compliance-fusion")
async def demo_compliance_fusion(
    tenant_id: str = "fce_demo",
    confirm: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    SitRep-FCE demo scenario.

    Demonstrates a modular compliance layer sitting between raw multi-sensor
    ingestion and downstream fusion analytics.

    Synthetic inputs:
    - radar / UNCLASSIFIED / open_network -> permit
    - EO/IR / PROTECTED_A / protected_a_network -> redact
    - SIGINT / PROTECTED_B / mission_network -> review_required / restricted
    """

    if not confirm:
        return {
            "status": "confirmation_required",
            "message": "Set confirm=true to run the SitRep-FCE compliance fusion demo.",
            "example": f"/api/v1/demo/compliance-fusion?tenant_id={tenant_id}&confirm=true",
        }

    synthetic_inputs = [
        {
            "source_system": "radar_sim",
            "source_type": "radar",
            "classification_in": "UNCLASSIFIED",
            "security_domain_in": "open_network",
            "requested_output_domain": "operator_console",
            "metadata": {
                "sensor_role": "primary track cue",
                "object_type": "vessel",
                "example_payload": {
                    "track_id": "RAD-FCE-001",
                    "latitude": 49.167,
                    "longitude": -123.932,
                    "confidence": 0.84,
                },
            },
        },
        {
            "source_system": "eo_ir_sim",
            "source_type": "eo_ir",
            "classification_in": "PROTECTED_A",
            "security_domain_in": "protected_a_network",
            "requested_output_domain": "operator_console",
            "metadata": {
                "sensor_role": "visual confirmation cue",
                "object_type": "vessel",
                "example_payload": {
                    "image_chip_id": "EOIR-FCE-001",
                    "sensitive_fields": ["raw_image_reference", "operator_notes"],
                    "confidence": 0.79,
                },
            },
        },
        {
            "source_system": "sigint_sim",
            "source_type": "sigint",
            "classification_in": "PROTECTED_B",
            "security_domain_in": "mission_network",
            "requested_output_domain": "operator_console",
            "metadata": {
                "sensor_role": "protected RF/SIGINT cue",
                "object_type": "vessel",
                "example_payload": {
                    "emitter_id": "SIG-FCE-001",
                    "frequency_band": "synthetic",
                    "sensitive_fields": ["emitter_signature", "collection_method"],
                    "confidence": 0.86,
                },
            },
        },
    ]

    decisions = []
    compliance_summary = {}

    for item in synthetic_inputs:
        decision = evaluate_compliance(
            source_system=item["source_system"],
            source_type=item["source_type"],
            classification_in=item["classification_in"],
            security_domain_in=item["security_domain_in"],
            requested_output_domain=item["requested_output_domain"],
            output_audience="operator_console",
            metadata=item["metadata"],
        )

        decision_dict = decision_to_dict(decision)

        result = await db.execute(
            text(
                """
                INSERT INTO compliance_audit_logs (
                    tenant_id,
                    policy_id,
                    policy_version,
                    rule_id,
                    source_system,
                    source_type,
                    classification_in,
                    classification_out,
                    security_domain_in,
                    requested_output_domain,
                    enforcement_action,
                    compliance_disposition,
                    reason,
                    human_readable_decision,
                    machine_readable_policy,
                    evidence
                )
                VALUES (
                    :tenant_id,
                    :policy_id,
                    :policy_version,
                    :rule_id,
                    :source_system,
                    :source_type,
                    :classification_in,
                    :classification_out,
                    :security_domain_in,
                    :requested_output_domain,
                    :enforcement_action,
                    :compliance_disposition,
                    :reason,
                    :human_readable_decision,
                    CAST(:machine_readable_policy AS jsonb),
                    CAST(:evidence AS jsonb)
                )
                RETURNING id, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "policy_id": decision.policy_id,
                "policy_version": decision.policy_version,
                "rule_id": decision.rule_id,
                "source_system": decision.source_system,
                "source_type": decision.source_type,
                "classification_in": decision.classification_in,
                "classification_out": decision.classification_out,
                "security_domain_in": decision.security_domain_in,
                "requested_output_domain": decision.requested_output_domain,
                "enforcement_action": decision.enforcement_action,
                "compliance_disposition": decision.compliance_disposition,
                "reason": decision.reason,
                "human_readable_decision": decision.human_readable_decision,
                "machine_readable_policy": json.dumps(decision.machine_readable_policy),
                "evidence": json.dumps(decision.evidence),
            },
        )

        row = result.mappings().one()

        action = decision.enforcement_action
        compliance_summary[action] = compliance_summary.get(action, 0) + 1

        if action == "permit":
            downstream_action = "allowed_to_fusion_pipeline"
        elif action == "redact":
            downstream_action = "allowed_to_fusion_pipeline_after_redaction"
        elif action == "segregate":
            downstream_action = "segregated_from_requested_output_domain"
        elif action == "review_required":
            downstream_action = "held_for_review_before_release_or_cross_domain_fusion"
        else:
            downstream_action = "restricted"

        decisions.append(
            {
                "audit_log_id": str(row["id"]),
                "audit_created_at": row["created_at"].isoformat(),
                "source_system": item["source_system"],
                "source_type": item["source_type"],
                "classification_in": item["classification_in"],
                "security_domain_in": item["security_domain_in"],
                "requested_output_domain": item["requested_output_domain"],
                "enforcement_action": decision.enforcement_action,
                "compliance_disposition": decision.compliance_disposition,
                "rule_id": decision.rule_id,
                "human_readable_decision": decision.human_readable_decision,
                "downstream_fusion_action": downstream_action,
                "decision": decision_dict,
            }
        )

    await db.commit()

    return {
        "status": "ok",
        "scenario": "sitrep_fce_compliance_fusion",
        "tenant_id": tenant_id,
        "description": (
            "Synthetic SitRep-FCE scenario demonstrating policy-aware compliance enforcement "
            "between raw multi-sensor ingestion and downstream fusion analytics."
        ),
        "input_modalities": ["radar", "eo_ir", "sigint"],
        "classification_levels_demonstrated": [
            "UNCLASSIFIED",
            "PROTECTED_A",
            "PROTECTED_B",
        ],
        "security_domains_demonstrated": [
            "open_network",
            "protected_a_network",
            "mission_network",
            "operator_console",
        ],
        "requested_output_domain": "operator_console",
        "compliance_summary": compliance_summary,
        "decisions": decisions,
        "audit_urls": {
            "audit_log": f"/api/v1/compliance/audit?tenant_id={tenant_id}",
            "audit_export": f"/api/v1/compliance/audit/export?tenant_id={tenant_id}",
        },
        "important_non_claims": [
            "Prototype uses synthetic unclassified demonstration data.",
            "Prototype models Protected B-style policy conditions but is not an accredited Protected B system.",
            "Prototype does not perform real classified downgrade.",
            "Prototype does not replace authorized release authorities.",
        ],
    }
