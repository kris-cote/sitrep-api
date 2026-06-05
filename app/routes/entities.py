from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.entity_detail import get_entity_detail
from app.dependencies import get_db
from app.db.lineage import get_entity_lineage
from app.db.entity_tracks import get_entity_track
from app.db.operator_actions import (
    create_operator_action_for_entity,
    get_operator_actions_for_entity,
)
from app.models.operator_action import OperatorActionCreate


router = APIRouter(prefix="/api/v1/entities", tags=["entities"])
@router.get("/{entity_id}")
async def read_entity_detail(
    entity_id: str,
    db: AsyncSession = Depends(get_db)
):
    entity = await get_entity_detail(db, entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return entity

@router.get("/{entity_id}/lineage")
async def read_entity_lineage(
    entity_id: str,
    db: AsyncSession = Depends(get_db)
):
    lineage = await get_entity_lineage(db, entity_id)

    if not lineage:
        raise HTTPException(status_code=404, detail="Entity not found")

    return lineage


@router.get("/{entity_id}/track")
async def read_entity_track(
    entity_id: str,
    db: AsyncSession = Depends(get_db)
):
    track = await get_entity_track(db, entity_id)

    if not track:
        raise HTTPException(status_code=404, detail="Entity not found")

    return track


@router.post("/{entity_id}/operator-action")
async def create_entity_operator_action(
    entity_id: str,
    action: OperatorActionCreate,
    db: AsyncSession = Depends(get_db)
):
    existing = await get_entity_track(db, entity_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Entity not found")

    action_id = await create_operator_action_for_entity(
        db=db,
        entity_id=entity_id,
        action_type=action.action_type,
        action_note=action.action_note,
        operator_id=action.operator_id or "operator",
        identity_label=action.identity_label,
        adjusted_confidence=action.adjusted_confidence,
    )

    return {
        "status": "ok",
        "entity_id": entity_id,
        "operator_action_id": action_id,
        "action_type": action.action_type,
    }


@router.get("/{entity_id}/operator-actions")
async def read_entity_operator_actions(
    entity_id: str,
    db: AsyncSession = Depends(get_db)
):
    existing = await get_entity_track(db, entity_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Entity not found")

    actions = await get_operator_actions_for_entity(db, entity_id)

    return {
        "entity_id": entity_id,
        "count": len(actions),
        "operator_actions": actions,
    }
