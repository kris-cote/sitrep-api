from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.db.cop import get_common_operating_picture


router = APIRouter(prefix="/api/v1/cop", tags=["common-operating-picture"])


@router.get("/")
async def read_common_operating_picture(
    tenant_id: str = Query(default="default"),
    status: str = Query(default="active"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    return await get_common_operating_picture(
        db=db,
        tenant_id=tenant_id,
        status=status,
        limit=limit,
    )
