import math
from typing import Optional, Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.spatiotemporal import evaluate_spatiotemporal_gate

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """
    Calculates approximate distance between two lat/lon points in kilometers.
    Good enough for first-pass track association.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 999999.0

    radius_km = 6371.0

    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radius_km * c


def score_association(
    observation: Dict[str, Any],
    entity: Dict[str, Any],
    max_distance_km: float = 5.0
) -> tuple[float, Dict[str, Any]]:
    """
    Association scoring with spatiotemporal gating.

    Returns:
    - score
    - gate_result
    """

    gate_result = evaluate_spatiotemporal_gate(observation, entity)

    if not gate_result.get("gate_passed"):
        return 0.0, gate_result

    score = 0.0

    obs_type = observation.get("object_type")
    ent_type = entity.get("entity_type")

    if obs_type and ent_type and obs_type == ent_type:
        score += 0.35

    distance_km = gate_result.get("distance_km", 999999.0)

    if distance_km <= max_distance_km:
        proximity_score = max(0.0, 1.0 - (float(distance_km) / max_distance_km))
        score += 0.45 * proximity_score

    existing_confidence = float(entity.get("current_confidence") or 0.0)
    score += 0.20 * existing_confidence

    # Slightly reward physically plausible movement.
    if gate_result.get("gate_status") == "kinematically_plausible":
        score += 0.05

    return round(min(score, 1.0), 4), gate_result

async def get_recent_active_entities(
    db: AsyncSession,
    object_type: Optional[str],
    tenant_id: str,
    limit: int = 50
):
    if object_type:
        query = text("""
            SELECT
                id,
                entity_type,
                identity_label,
                status,
                first_seen_at,
                last_seen_at,
                current_latitude,
                current_longitude,
                current_altitude_m,
                current_confidence,
                tenant_id
            FROM entities
            WHERE status = 'active'
              AND tenant_id = :tenant_id
              AND entity_type = :object_type
            ORDER BY updated_at DESC
            LIMIT :limit
        """)

        params = {
            "object_type": object_type,
            "tenant_id": tenant_id,
            "limit": limit,
        }

    else:
        query = text("""
            SELECT
                id,
                entity_type,
                identity_label,
                status,
                first_seen_at,
                last_seen_at,
                current_latitude,
                current_longitude,
                current_altitude_m,
                current_confidence,
                tenant_id
            FROM entities
            WHERE status = 'active'
              AND tenant_id = :tenant_id
            ORDER BY updated_at DESC
            LIMIT :limit
        """)

        params = {
            "tenant_id": tenant_id,
            "limit": limit,
        }

    result = await db.execute(query, params)

    return [dict(row._mapping) for row in result.fetchall()]

async def get_active_track_for_entity(db: AsyncSession, entity_id: str) -> Optional[str]:
    query = text("""
        SELECT id
        FROM tracks
        WHERE entity_id = :entity_id
          AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 1
    """)

    result = await db.execute(query, {"entity_id": entity_id})
    row = result.fetchone()

    return str(row[0]) if row else None


async def create_entity_with_track(
    db: AsyncSession,
    observation_id: str,
    observation: Dict[str, Any],
):
    query_entity = text("""
        INSERT INTO entities (
            entity_type,
            identity_label,
            status,
            first_seen_at,
            last_seen_at,
            current_latitude,
            current_longitude,
            current_altitude_m,
            current_confidence,
            tenant_id
        )
        VALUES (
            :entity_type,
            'unknown',
            'active',
            :collected_at,
            :collected_at,
            :latitude,
            :longitude,
            :altitude_m,
            :confidence,
            :tenant_id
        )
        RETURNING id
    """)

    result = await db.execute(
        query_entity,
        {
            "entity_type": observation.get("object_type") or "unknown",
            "collected_at": observation.get("collected_at"),
            "latitude": observation.get("latitude"),
            "longitude": observation.get("longitude"),
            "altitude_m": observation.get("altitude_m"),
            "confidence": observation.get("confidence") or 0.5,
            "tenant_id": observation.get("tenant_id") or "default",
        }
    )

    entity_id = str(result.fetchone()[0])

    query_track = text("""
        INSERT INTO tracks (entity_id, status)
        VALUES (:entity_id, 'active')
        RETURNING id
    """)

    result = await db.execute(query_track, {"entity_id": entity_id})
    track_id = str(result.fetchone()[0])

    await add_track_point(
        db=db,
        track_id=track_id,
        observation_id=observation_id,
        observation=observation
    )

    await add_association(
        db=db,
        observation_id=observation_id,
        entity_id=entity_id,
        score=1.0,
        reason="Created new entity and track from first observation."
    )

    return entity_id, track_id


async def update_entity_track(
    db: AsyncSession,
    observation_id: str,
    observation: Dict[str, Any],
    entity_id: str,
    association_score: float,
    gate_result: Dict[str, Any] | None = None,
):
    track_id = await get_active_track_for_entity(db, entity_id)

    if not track_id:
        query_track = text("""
            INSERT INTO tracks (entity_id, status)
            VALUES (:entity_id, 'active')
            RETURNING id
        """)

        result = await db.execute(query_track, {"entity_id": entity_id})
        track_id = str(result.fetchone()[0])

    await add_track_point(
        db=db,
        track_id=track_id,
        observation_id=observation_id,
        observation=observation
    )

    query_update_entity = text("""
        UPDATE entities
        SET
            last_seen_at = :collected_at,
            current_latitude = :latitude,
            current_longitude = :longitude,
            current_altitude_m = :altitude_m,
            current_confidence = LEAST(1.0, ((current_confidence + :confidence) / 2.0) + 0.05),
            updated_at = now()
        WHERE id = :entity_id
    """)

    await db.execute(
        query_update_entity,
        {
            "entity_id": entity_id,
            "collected_at": observation.get("collected_at"),
            "latitude": observation.get("latitude"),
            "longitude": observation.get("longitude"),
            "altitude_m": observation.get("altitude_m"),
            "confidence": observation.get("confidence") or 0.5,
        }
    )

    gate_reason = ""
    if gate_result:
        gate_reason = (
            f" Spatiotemporal gate: {gate_result.get('gate_status')} - "
            f"{gate_result.get('gate_reason')}"
        )

    await add_association(
        db=db,
        observation_id=observation_id,
        entity_id=entity_id,
        score=association_score,
        reason=(
            "Associated observation to existing active entity using type, spatial proximity, "
            "confidence, and spatiotemporal plausibility."
            + gate_reason
        )
    )

    return entity_id, track_id

async def add_track_point(
    db: AsyncSession,
    track_id: str,
    observation_id: str,
    observation: Dict[str, Any],
):
    features = observation.get("features") or {}

    query = text("""
        INSERT INTO track_points (
            track_id,
            observation_id,
            recorded_at,
            latitude,
            longitude,
            altitude_m,
            speed_knots,
            heading_degrees,
            confidence
        )
        VALUES (
            :track_id,
            :observation_id,
            :recorded_at,
            :latitude,
            :longitude,
            :altitude_m,
            :speed_knots,
            :heading_degrees,
            :confidence
        )
    """)

    await db.execute(
        query,
        {
            "track_id": track_id,
            "observation_id": observation_id,
            "recorded_at": observation.get("collected_at"),
            "latitude": observation.get("latitude"),
            "longitude": observation.get("longitude"),
            "altitude_m": observation.get("altitude_m"),
            "speed_knots": features.get("speed_knots"),
            "heading_degrees": features.get("heading_degrees"),
            "confidence": observation.get("confidence") or 0.5,
        }
    )


async def add_association(
    db: AsyncSession,
    observation_id: str,
    entity_id: str,
    score: float,
    reason: str,
):
    query = text("""
        INSERT INTO associations (
            observation_id,
            entity_id,
            association_score,
            association_reason
        )
        VALUES (
            :observation_id,
            :entity_id,
            :association_score,
            :association_reason
        )
    """)

    await db.execute(
        query,
        {
            "observation_id": observation_id,
            "entity_id": entity_id,
            "association_score": score,
            "association_reason": reason,
        }
    )


async def associate_observation_to_entity(
    db: AsyncSession,
    observation_id: str,
    observation: Dict[str, Any],
):
    tenant_id = observation.get("tenant_id") or "default"
    object_type = observation.get("object_type")

    candidates = await get_recent_active_entities(
        db=db,
        object_type=object_type,
        tenant_id=tenant_id,
    )

    best_entity = None
    best_score = 0.0
    best_gate_result = None

    for entity in candidates:
        score, gate_result = score_association(observation, entity)

        if score > best_score:
            best_score = score
            best_entity = entity
            best_gate_result = gate_result

    threshold = 0.60

    if best_entity and best_score >= threshold:
        entity_id, track_id = await update_entity_track(
            db=db,
            observation_id=observation_id,
            observation=observation,
            entity_id=str(best_entity["id"]),
            association_score=best_score,
            gate_result=best_gate_result,
        )

        return {
            "association": "matched_existing_entity",
            "association_score": best_score,
            "entity_id": entity_id,
            "track_id": track_id,
            "gate_result": best_gate_result,
        }

    entity_id, track_id = await create_entity_with_track(
        db=db,
        observation_id=observation_id,
        observation=observation,
    )

    return {
        "association": "created_new_entity",
        "association_score": 1.0,
        "entity_id": entity_id,
        "track_id": track_id,
        "gate_result": {
            "gate_passed": True,
            "gate_status": "new_entity",
            "distance_km": None,
            "time_delta_seconds": None,
            "estimated_speed_knots": None,
            "max_allowed_speed_knots": None,
            "gate_reason": "No existing active entity met the association threshold; new entity created.",
        },
    }
