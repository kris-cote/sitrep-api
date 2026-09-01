from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.observation import ObservationCreate
from app.services.observation_pipeline import process_observation


router = APIRouter(prefix="/api/v1/observations", tags=["observations"])


@router.post("/")
async def create_observation(
    observation: ObservationCreate,
    db: AsyncSession = Depends(get_db),
):
    return await process_observation(db, observation.model_dump())
