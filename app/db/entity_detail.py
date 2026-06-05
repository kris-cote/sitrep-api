from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_entity_detail(db: AsyncSession, entity_id: str):
    query = text("""
        SELECT
            id AS entity_id,
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

    result = await db.execute(query, {"entity_id": entity_id})
    row = result.fetchone()

    if not row:
        return None

    return dict(row._mapping)
