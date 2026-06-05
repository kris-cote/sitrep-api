from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.observation import ObservationCreate
from app.db.observations import insert_observation
from app.db.tracking import associate_observation_to_entity
from app.db.fusion import create_fusion_output_with_provenance
from app.dependencies import get_db


router = APIRouter(prefix="/api/v1/observations", tags=["observations"])


@router.post("/")
async def create_observation(
    observation: ObservationCreate,
    db: AsyncSession = Depends(get_db)
):
    observation_data = observation.dict()

    obs_id = await insert_observation(db, observation_data)

    tracking_result = await associate_observation_to_entity(
        db=db,
        observation_id=obs_id,
        observation=observation_data,
    )

    fusion_result = await create_fusion_output_with_provenance(
        db=db,
        entity_id=tracking_result["entity_id"],
        observation_id=obs_id,
        association=tracking_result["association"],
        association_score=tracking_result["association_score"],
        object_type=observation_data.get("object_type") or "unknown",
        source_system=observation_data.get("source_system"),
        source_type=observation_data.get("source_type"),
        confidence=observation_data.get("confidence") or 0.5,
        classification_tag=observation_data.get("classification_tag") or "UNCLASSIFIED",
        gate_result=tracking_result.get("gate_result"),
        tenant_id=observation_data.get("tenant_id") or "default",
    )

    return {
        "status": "ok",
        "observation_id": obs_id,
        **tracking_result,
        **fusion_result,
    }
