from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.models.db import get_session
from app.services.operational_forecast import forecast_operational_demand

router = APIRouter(prefix="/operational-forecast", tags=["operational-forecast"])


@router.get("/resources")
def get_operational_resource_forecast(
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    horizons: str = Query(default="0.5,2,6,24", description="Comma-separated forecast horizons in hours"),
    max_situations: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    parsed = []
    for value in horizons.split(","):
        value = value.strip()
        if not value:
            continue
        parsed.append(float(value))
    parsed = [h for h in parsed if 0 < h <= 168]
    return forecast_operational_demand(
        session=session,
        tenant_id=tenant_id,
        horizons_hours=parsed,
        max_situations=max_situations,
    )
