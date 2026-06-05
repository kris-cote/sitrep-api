from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_common_operating_picture(
    db: AsyncSession,
    tenant_id: str = "default",
    status: str = "active",
    limit: int = 100,
):
    query = text("""
        WITH entity_observation_summary AS (
            SELECT
                a.entity_id,
                COUNT(DISTINCT o.id) AS observation_count,
                ARRAY_AGG(DISTINCT o.source_system) AS source_systems,
                ARRAY_AGG(DISTINCT o.source_type) AS source_types,
                MAX(o.collected_at) AS latest_observation_at
            FROM associations a
            JOIN observations o ON o.id = a.observation_id
            GROUP BY a.entity_id
        ),

        track_summary AS (
            SELECT
                t.entity_id,
                COUNT(tp.id) AS track_point_count,
                MAX(tp.recorded_at) AS latest_track_point_at
            FROM tracks t
            LEFT JOIN track_points tp ON tp.track_id = t.id
            GROUP BY t.entity_id
        ),

        latest_track_point AS (
            SELECT DISTINCT ON (t.entity_id)
                t.entity_id,
                tp.recorded_at AS latest_recorded_at,
                tp.latitude AS latest_latitude,
                tp.longitude AS latest_longitude,
                tp.altitude_m AS latest_altitude_m,
                tp.confidence AS latest_track_confidence
            FROM tracks t
            JOIN track_points tp ON tp.track_id = t.id
            ORDER BY t.entity_id, tp.recorded_at DESC
        ),
        latest_fusion AS (
            SELECT DISTINCT ON (fo.entity_id)
                fo.entity_id,
                fo.id AS fusion_id,
                fo.assessment,
                fo.confidence AS fusion_confidence,
                fo.explanation,
                fo.created_at AS fusion_created_at
            FROM fusion_outputs fo
            LEFT JOIN LATERAL jsonb_array_elements(fo.evidence) AS ev ON true
            LEFT JOIN observations o
                ON o.id::text = ev->>'observation_id'
            ORDER BY fo.entity_id, o.collected_at DESC NULLS LAST, fo.created_at DESC, fo.id DESC
        ),
        latest_provenance AS (
            SELECT DISTINCT ON (fo.entity_id)
                fo.entity_id,
                pr.id AS provenance_id,
                pr.output_id,
                pr.created_at AS provenance_created_at
            FROM fusion_outputs fo
            JOIN provenance_records pr ON pr.output_id = fo.id
            LEFT JOIN LATERAL jsonb_array_elements(fo.evidence) AS ev ON true
            LEFT JOIN observations o
                ON o.id::text = ev->>'observation_id'
            WHERE pr.output_type = 'fusion_output'
            ORDER BY fo.entity_id, o.collected_at DESC NULLS LAST, pr.created_at DESC, pr.id DESC
        )

        SELECT
            e.id AS entity_id,
            e.entity_type,
            e.identity_label,
            e.status,
            e.first_seen_at,
            COALESCE(ltp.latest_recorded_at, e.last_seen_at) AS last_seen_at,
            COALESCE(ltp.latest_latitude, e.current_latitude) AS current_latitude,
            COALESCE(ltp.latest_longitude, e.current_longitude) AS current_longitude,
            COALESCE(ltp.latest_altitude_m, e.current_altitude_m) AS current_altitude_m,
            e.current_confidence,
            e.tenant_id,

            COALESCE(eos.observation_count, 0) AS observation_count,
            COALESCE(ts.track_point_count, 0) AS track_point_count,

            COALESCE(eos.source_systems, ARRAY[]::text[]) AS source_systems,
            COALESCE(eos.source_types, ARRAY[]::text[]) AS source_types,

            eos.latest_observation_at,
            ts.latest_track_point_at,

            lf.fusion_id,
            lf.assessment AS latest_assessment,
            lf.fusion_confidence,
            eos.latest_observation_at,
            ts.latest_track_point_at,

            lf.explanation AS latest_explanation,
            lf.fusion_created_at,

            lp.provenance_id,
            lp.provenance_created_at

        FROM entities e
        LEFT JOIN entity_observation_summary eos ON eos.entity_id = e.id
        LEFT JOIN track_summary ts ON ts.entity_id = e.id
        LEFT JOIN latest_fusion lf ON lf.entity_id = e.id
        LEFT JOIN latest_provenance lp ON lp.entity_id = e.id
        LEFT JOIN latest_track_point ltp ON ltp.entity_id = e.id
        WHERE e.tenant_id = :tenant_id
          AND e.status = :status

        ORDER BY e.updated_at DESC
        LIMIT :limit
    """)

    result = await db.execute(
        query,
        {
            "tenant_id": tenant_id,
            "status": status,
            "limit": limit,
        },
    )

    rows = [dict(row._mapping) for row in result.fetchall()]

    return {
        "tenant_id": tenant_id,
        "status": status,
        "count": len(rows),
        "entities": rows,
    }
