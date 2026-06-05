from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


DEFAULT_TRUST_BY_TYPE = {
    "radar": 0.88,
    "eo_video": 0.90,
    "eo_ir": 0.90,
    "rf_detection": 0.78,
    "sigint": 0.78,
    "operator_report": 0.70,
    "text_report": 0.70,
    "telemetry": 0.84,
    "satellite": 0.86,
    "sonar": 0.76,
    "unknown": 0.75,
}


async def get_source_trust_weight(
    db: AsyncSession,
    source_system: str | None,
    source_type: str | None,
) -> float:
    if source_system:
        query = text("""
            SELECT trust_weight
            FROM source_systems
            WHERE name = :source_system
            LIMIT 1
        """)

        result = await db.execute(query, {"source_system": source_system})
        row = result.fetchone()

        if row and row[0] is not None:
            return float(row[0])

    return float(DEFAULT_TRUST_BY_TYPE.get(source_type or "unknown", 0.75))
