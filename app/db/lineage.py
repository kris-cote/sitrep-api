from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_entity_lineage(db: AsyncSession, entity_id: str):
    entity_query = text("""
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
            tenant_id,
            created_at,
            updated_at
        FROM entities
        WHERE id = :entity_id
        LIMIT 1
    """)

    entity_result = await db.execute(entity_query, {"entity_id": entity_id})
    entity_row = entity_result.fetchone()

    if not entity_row:
        return None

    entity = dict(entity_row._mapping)

    observations_query = text("""
        SELECT
            o.id,
            o.source_system,
            o.source_type,
            o.object_type,
            o.collected_at,
            o.ingested_at,
            o.latitude,
            o.longitude,
            o.altitude_m,
            o.confidence,
            o.features,
            o.raw_payload,
            o.classification_tag,
            o.tenant_id,
            a.association_score,
            a.association_reason,
            a.created_at AS associated_at
        FROM associations a
        JOIN observations o ON o.id = a.observation_id
        WHERE a.entity_id = :entity_id
        ORDER BY o.collected_at ASC
    """)

    observations_result = await db.execute(observations_query, {"entity_id": entity_id})
    observations = [dict(row._mapping) for row in observations_result.fetchall()]

    track_query = text("""
        SELECT
            t.id AS track_id,
            t.status AS track_status,
            t.started_at,
            t.ended_at,
            tp.id AS track_point_id,
            tp.observation_id,
            tp.recorded_at,
            tp.latitude,
            tp.longitude,
            tp.altitude_m,
            tp.speed_knots,
            tp.heading_degrees,
            tp.confidence
        FROM tracks t
        LEFT JOIN track_points tp ON tp.track_id = t.id
        WHERE t.entity_id = :entity_id
        ORDER BY tp.recorded_at ASC
    """)

    track_result = await db.execute(track_query, {"entity_id": entity_id})
    track_points = [dict(row._mapping) for row in track_result.fetchall()]

    source_types = sorted(list({obs["source_type"] for obs in observations if obs.get("source_type")}))
    source_systems = sorted(list({obs["source_system"] for obs in observations if obs.get("source_system")}))

    explanation = (
        f"Entity {entity_id} is a persistent {entity.get('entity_type')} track "
        f"formed from {len(observations)} associated observations across "
        f"{len(source_types)} modality type(s): {', '.join(source_types) or 'unknown'}. "
        f"Sources include: {', '.join(source_systems) or 'unknown'}."
    )

    return {
        "entity": entity,
        "observations": observations,
        "track_points": track_points,
        "source_systems": source_systems,
        "source_types": source_types,
        "explanation": explanation,
    }
