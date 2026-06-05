import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def insert_observation(db: AsyncSession, data: dict):
    safe_data = dict(data)

    safe_data["features"] = json.dumps(safe_data.get("features") or {})
    safe_data["raw_payload"] = json.dumps(safe_data.get("raw_payload") or {})

    query = text("""
        INSERT INTO observations (
            source_system,
            source_type,
            object_type,
            collected_at,
            latitude,
            longitude,
            altitude_m,
            confidence,
            features,
            raw_payload,
            classification_tag,
            tenant_id
        )
        VALUES (
            :source_system,
            :source_type,
            :object_type,
            :collected_at,
            :latitude,
            :longitude,
            :altitude_m,
            :confidence,
            CAST(:features AS jsonb),
            CAST(:raw_payload AS jsonb),
            :classification_tag,
            :tenant_id
        )
        RETURNING id
    """)

    result = await db.execute(query, safe_data)
    row = result.fetchone()

    return str(row[0])
