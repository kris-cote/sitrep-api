import json
from sqlalchemy import text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession


def normalize_jsonb(value):
    """
    asyncpg usually returns JSONB as Python dict/list.
    This protects us in case it comes back as a string.
    """
    if value is None:
        return None

    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value

    return value


async def get_provenance_by_id(db: AsyncSession, provenance_id: str):
    query = text("""
        SELECT
            pr.id AS provenance_id,
            pr.output_type,
            pr.output_id,
            pr.derived_from_observations,
            pr.processing_steps,
            pr.policy_context,
            pr.created_at,

            fo.entity_id,
            fo.assessment,
            fo.confidence AS fusion_confidence,
            fo.explanation,
            fo.evidence,
            fo.tenant_id,
            fo.created_at AS fusion_created_at

        FROM provenance_records pr
        LEFT JOIN fusion_outputs fo ON fo.id = pr.output_id
        WHERE pr.id = :provenance_id
        LIMIT 1
    """)

    result = await db.execute(query, {"provenance_id": provenance_id})
    row = result.fetchone()

    if not row:
        return None

    record = dict(row._mapping)

    record["derived_from_observations"] = normalize_jsonb(
        record.get("derived_from_observations")
    ) or []

    record["processing_steps"] = normalize_jsonb(
        record.get("processing_steps")
    ) or []

    record["policy_context"] = normalize_jsonb(
        record.get("policy_context")
    ) or {}

    record["evidence"] = normalize_jsonb(
        record.get("evidence")
    ) or []

    observation_ids = [str(x) for x in record["derived_from_observations"]]

    observations = []

    if observation_ids:
        obs_query = text("""
            SELECT
                id,
                source_system,
                source_type,
                object_type,
                collected_at,
                ingested_at,
                latitude,
                longitude,
                altitude_m,
                confidence,
                features,
                raw_payload,
                classification_tag,
                tenant_id
            FROM observations
            WHERE id::text IN :observation_ids
            ORDER BY collected_at ASC
        """).bindparams(bindparam("observation_ids", expanding=True))

        obs_result = await db.execute(
            obs_query,
            {"observation_ids": observation_ids}
        )

        observations = [dict(row._mapping) for row in obs_result.fetchall()]

    source_systems = sorted(
        list({obs.get("source_system") for obs in observations if obs.get("source_system")})
    )

    source_types = sorted(
        list({obs.get("source_type") for obs in observations if obs.get("source_type")})
    )

    return {
        "provenance": record,
        "source_systems": source_systems,
        "source_types": source_types,
        "observations": observations,
        "trace_summary": {
            "observation_count": len(observations),
            "processing_step_count": len(record["processing_steps"]),
            "source_system_count": len(source_systems),
            "source_type_count": len(source_types),
        },
        "explanation": (
            f"Provenance record {provenance_id} links fusion output "
            f"{record.get('output_id')} to {len(observations)} source observation(s) "
            f"across {len(source_types)} modality type(s): "
            f"{', '.join(source_types) or 'unknown'}."
        ),
    }


async def get_provenance_by_fusion_id(db: AsyncSession, fusion_id: str):
    query = text("""
        SELECT id
        FROM provenance_records
        WHERE output_type = 'fusion_output'
          AND output_id = :fusion_id
        ORDER BY created_at DESC
        LIMIT 1
    """)

    result = await db.execute(query, {"fusion_id": fusion_id})
    row = result.fetchone()

    if not row:
        return None

    return await get_provenance_by_id(db, str(row[0]))
