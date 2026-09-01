from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.models.db import get_session
from app.services.scenario_simulation import simulate_scenario

router = APIRouter(prefix="/scenario-simulation", tags=["scenario-simulation"])


class SituationChange(BaseModel):
    situation_id: str
    risk_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    urgency_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    severity: Optional[str] = None
    radius_km: Optional[float] = Field(default=None, ge=0.0, le=5000.0)
    forecast_trend: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    context: Dict[str, Any] = {}


class ResourceChange(BaseModel):
    capability_id: str
    availability_status: Optional[str] = None
    availability_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    readiness_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    capacity_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    suitability_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class InfrastructureChange(BaseModel):
    feature_id: Optional[str] = None
    state: str = "degraded"
    impact_type: str = "availability"
    notes: Optional[str] = None


class ScenarioRequest(BaseModel):
    tenant_id: str = "default"
    situation_changes: List[SituationChange] = []
    resource_changes: List[ResourceChange] = []
    infrastructure_changes: List[InfrastructureChange] = []
    horizons_hours: List[float] = [0.5, 2.0, 6.0, 24.0]


@router.post("/run")
def run_scenario(payload: ScenarioRequest, session: Session = Depends(get_session)):
    return simulate_scenario(
        session=session,
        tenant_id=payload.tenant_id,
        situation_changes=[item.model_dump(exclude_none=True) for item in payload.situation_changes],
        resource_changes=[item.model_dump(exclude_none=True) for item in payload.resource_changes],
        infrastructure_changes=[item.model_dump(exclude_none=True) for item in payload.infrastructure_changes],
        horizons_hours=payload.horizons_hours,
    )
