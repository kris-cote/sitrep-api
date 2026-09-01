from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.models.db import get_session
from app.services.resource_optimizer import optimize_resource_plan

router = APIRouter(prefix="/resource-optimizer", tags=["resource-optimizer"])


@router.get("/plan")
def get_resource_optimization_plan(
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    max_distance_km: float = Query(default=300.0, gt=0, le=2000),
    max_situations: int = Query(default=100, ge=1, le=500),
    max_candidates_per_situation: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
):
    return optimize_resource_plan(
        session=session,
        tenant_id=tenant_id,
        max_distance_km=max_distance_km,
        max_situations=max_situations,
        max_candidates_per_situation=max_candidates_per_situation,
    )
