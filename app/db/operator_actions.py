from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create_operator_action_for_entity(
    db: AsyncSession,
    entity_id: str,
    action_type: str,
    action_note: str | None = None,
    operator_id: str = "operator",
    identity_label: str | None = None,
    adjusted_confidence: float | None = None,
):
    action_query = text("""
        INSERT INTO operator_actions (
            entity_id,
            action_type,
            action_note,
            operator_id
        )
        VALUES (
            :entity_id,
            :action_type,
            :action_note,
            :operator_id
        )
        RETURNING id
    """)

    result = await db.execute(
        action_query,
        {
            "entity_id": entity_id,
            "action_type": action_type,
            "action_note": action_note,
            "operator_id": operator_id,
        }
    )

    action_id = str(result.fetchone()[0])

    updates = []
    params = {"entity_id": entity_id}

    if identity_label:
        updates.append("identity_label = :identity_label")
        params["identity_label"] = identity_label

    if adjusted_confidence is not None:
        updates.append("current_confidence = :adjusted_confidence")
        params["adjusted_confidence"] = adjusted_confidence

    if action_type == "confirm" and adjusted_confidence is None:
        updates.append("current_confidence = LEAST(1.0, current_confidence + 0.05)")

    if action_type == "reject":
        updates.append("status = 'rejected'")

    if action_type == "flag":
        updates.append("status = 'flagged'")

    if updates:
        updates.append("updated_at = now()")

        update_query = text(f"""
            UPDATE entities
            SET {", ".join(updates)}
            WHERE id = :entity_id
        """)

        await db.execute(update_query, params)

    return action_id


async def get_operator_actions_for_entity(
    db: AsyncSession,
    entity_id: str,
):
    query = text("""
        SELECT
            id,
            entity_id,
            observation_id,
            fusion_output_id,
            action_type,
            action_note,
            operator_id,
            created_at
        FROM operator_actions
        WHERE entity_id = :entity_id
        ORDER BY created_at ASC
    """)

    result = await db.execute(query, {"entity_id": entity_id})

    return [dict(row._mapping) for row in result.fetchall()]
