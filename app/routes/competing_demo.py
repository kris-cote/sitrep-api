from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.models.db import get_session
from app.models.situation import SituationAudit, SituationRecord


router = APIRouter(prefix="/situations/demo", tags=["situations"])


@router.post("/wildfire-secondary", status_code=201)
def create_secondary_demo_wildfire(session: Session = Depends(get_session)):
    """Create a second synthetic wildfire that competes for the first demo's shared resources."""
    situation = SituationRecord(
        tenant_id="default",
        domain="wildfire",
        status="active",
        title="Demo: North-Central Vancouver Island Wildfire",
        summary=(
            "SIMULATED TRAINING SCENARIO: A second wildfire is escalating north-west of the original demo incident. "
            "The scenario is intentionally positioned within the same regional resource catchment so crews, aviation, "
            "medical support and reception-centre capacity must be prioritized across simultaneous incidents."
        ),
        latitude=49.4350,
        longitude=-124.3550,
        radius_km=24.0,
        confidence=0.84,
        risk_score=0.82,
        urgency_score=0.88,
        severity="critical",
        source_types=["demo", "simulated"],
        correlation_reasons=["competing incident training", "shared resource contention validation"],
        evidence=[{
            "type": "simulation_notice",
            "source": "sitrep-demo",
            "statement": "This is synthetic training data and not a live emergency.",
            "confidence": 1.0,
        }],
        context={
            "simulation": True,
            "training_only": True,
            "shared_resource_test": True,
            "forecast_trend": "rapidly_worsening",
            "weather": {
                "wind_from_deg": 285,
                "wind_speed_kmh": 42,
                "forecast_note": "Simulated stronger winds than the original demo incident",
            },
            "objectives": [
                "Force shared-resource prioritization",
                "Compare response-package coverage across simultaneous incidents",
                "Expose capability shortfalls and residual capacity",
                "Require human approval for all proposed allocations",
            ],
        },
    )
    session.add(situation)
    session.flush()
    session.add(SituationAudit(
        situation_id=situation.id,
        action="demo_competing_created",
        note="Synthetic competing wildfire created for shared-resource optimization testing",
        payload={"simulation": True, "training_only": True, "shared_resource_test": True},
    ))
    session.commit()
    session.refresh(situation)
    return situation
