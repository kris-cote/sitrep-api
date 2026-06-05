from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_entity_track(db: AsyncSession, entity_id: str):
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
            current_confidence
        FROM entities
        WHERE id = :entity_id
        LIMIT 1
    """)

    entity_result = await db.execute(entity_query, {"entity_id": entity_id})
    entity_row = entity_result.fetchone()

    if not entity_row:
        return None

    entity = dict(entity_row._mapping)

    points_query = text("""
        SELECT
            tp.id AS track_point_id,
            tp.track_id,
            tp.observation_id,
            tp.recorded_at,
            tp.latitude,
            tp.longitude,
            tp.altitude_m,
            tp.speed_knots,
            tp.heading_degrees,
            tp.confidence,

            o.source_system,
            o.source_type,
            o.object_type,
            o.features,
            o.raw_payload,

            a.association_score,
            a.association_reason

        FROM tracks t
        JOIN track_points tp ON tp.track_id = t.id
        LEFT JOIN observations o ON o.id = tp.observation_id
        LEFT JOIN associations a
            ON a.observation_id = tp.observation_id
            AND a.entity_id = t.entity_id

        WHERE t.entity_id = :entity_id
        ORDER BY tp.recorded_at ASC
    """)

    points_result = await db.execute(points_query, {"entity_id": entity_id})
    points = [dict(row._mapping) for row in points_result.fetchall()]

    return {
        "entity": entity,
        "track_point_count": len(points),
        "track_points": points,
    }
