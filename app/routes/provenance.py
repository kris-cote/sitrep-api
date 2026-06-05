from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.db.provenance import (
    get_provenance_by_id,
    get_provenance_by_fusion_id,
)


router = APIRouter(tags=["provenance"])


@router.get("/api/v1/provenance/{provenance_id}")
async def read_provenance(
    provenance_id: str,
    db: AsyncSession = Depends(get_db),
):
    provenance = await get_provenance_by_id(db, provenance_id)

    if not provenance:
        raise HTTPException(status_code=404, detail="Provenance record not found")

    return provenance


@router.get("/api/v1/fusion/{fusion_id}/provenance")
async def read_fusion_provenance(
    fusion_id: str,
    db: AsyncSession = Depends(get_db),
):
    provenance = await get_provenance_by_fusion_id(db, fusion_id)

    if not provenance:
        raise HTTPException(status_code=404, detail="Provenance record not found")

    return provenance
