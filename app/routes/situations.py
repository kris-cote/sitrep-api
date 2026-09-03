from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.exposure import ExposureAsset
from app.models.resource_capability import ResponseResourceCapability
from app.models.situation import SituationAudit, SituationRecord
from app.services.exposure_enrichment import enrich_situation_exposure
from app.services.wildfire_projection import wildfire_exposure_screen
from app.services.situation_impact import analyze_situation_infrastructure_impact
from app.services.resource_availability import situation_resource_profile


router = APIRouter(prefix="/situations", tags=["situations"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SituationCreate(BaseModel):
    tenant_id: str = "default"
    mission_id: Optional[str] = None
    domain: str = Field(default="general", min_length=2, max_length=80)
    title: str = Field(min_length=3, max_length=300)
    summary: str = Field(default="", max_length=12000)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(default=25.0, gt=0, le=1000)
    confidence: float = Field(default=0.0, ge=0, le=1)
    risk_score: float = Field(default=0.0, ge=0, le=1)
    urgency_score: float = Field(default=0.0, ge=0, le=1)
    severity: str = Field(default="low", min_length=2, max_length=40)
    source_types: List[str] = Field(default_factory=list)
    observation_ids: List[str] = Field(default_factory=list)
    correlation_reasons: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)


class SituationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=300)
    summary: Optional[str] = Field(default=None, max_length=12000)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_km: Optional[float] = Field(default=None, gt=0, le=1000)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    risk_score: Optional[float] = Field(default=None, ge=0, le=1)
    urgency_score: Optional[float] = Field(default=None, ge=0, le=1)
    severity: Optional[str] = Field(default=None, min_length=2, max_length=40)
    domain: Optional[str] = Field(default=None, min_length=2, max_length=80)
    source_types: Optional[List[str]] = None
    observation_ids: Optional[List[str]] = None
    correlation_reasons: Optional[List[str]] = None
    evidence: Optional[List[Dict[str, Any]]] = None
    context: Optional[Dict[str, Any]] = None
    note: str = Field(default="", max_length=4000)


class SituationStatusChange(BaseModel):
    note: str = Field(default="", max_length=4000)
    actor: str = Field(default="operator", min_length=2, max_length=200)


class DemoWildfireRequest(BaseModel):
    tenant_id: str = "default"
    title: str = "Demo: Central Vancouver Island Wildfire"
    latitude: float = Field(default=49.1659, ge=-90, le=90)
    longitude: float = Field(default=-124.0558, ge=-180, le=180)
    radius_km: float = Field(default=20.0, gt=0, le=500)


def _audit(session: Session, situation_id: str, action: str, note: str = "", payload: Optional[Dict[str, Any]] = None) -> None:
    session.add(SituationAudit(
        situation_id=situation_id,
        action=action,
        note=note,
        payload=payload or {},
    ))


def _demo_resource_specs(situation: SituationRecord) -> List[Dict[str, Any]]:
    lat = float(situation.latitude or 49.1659)
    lon = float(situation.longitude or -124.0558)
    return [
        {
            "asset_type": "fire_station", "name": "SIM Fire Base Alpha", "lat": lat + 0.16, "lon": lon - 0.05,
            "resource_type": "wildland_fire_crew", "capability_name": "SIM Initial Attack Crew Alpha",
            "capabilities": ["wildland_suppression", "structure_protection", "initial_attack"],
            "availability": "available", "availability_score": 0.95, "readiness": 0.92, "capacity": 0.82, "suitability": 0.94,
            "capacity_detail": {"crews": 2, "personnel": 8},
        },
        {
            "asset_type": "fire_station", "name": "SIM Fire Base Bravo", "lat": lat - 0.22, "lon": lon + 0.09,
            "resource_type": "wildland_fire_crew", "capability_name": "SIM Sustained Action Crew Bravo",
            "capabilities": ["wildland_suppression", "hose_lay", "structure_protection"],
            "availability": "limited", "availability_score": 0.72, "readiness": 0.80, "capacity": 0.88, "suitability": 0.86,
            "capacity_detail": {"crews": 3, "personnel": 12},
        },
        {
            "asset_type": "heliport", "name": "SIM Rotary Wing Base", "lat": lat + 0.28, "lon": lon + 0.12,
            "resource_type": "rotary_wing", "capability_name": "SIM Helicopter 01",
            "capabilities": ["bucket_operations", "reconnaissance", "crew_transport"],
            "availability": "available", "availability_score": 0.90, "readiness": 0.90, "capacity": 0.78, "suitability": 0.91,
            "capacity_detail": {"aircraft": 1, "bucket_litres": 1400},
        },
        {
            "asset_type": "airport", "name": "SIM Air Operations Base", "lat": lat - 0.36, "lon": lon - 0.18,
            "resource_type": "fixed_wing", "capability_name": "SIM Air Tanker Package",
            "capabilities": ["retardant_delivery", "aerial_reconnaissance"],
            "availability": "limited", "availability_score": 0.68, "readiness": 0.76, "capacity": 0.90, "suitability": 0.84,
            "capacity_detail": {"aircraft": 2},
        },
        {
            "asset_type": "hospital", "name": "SIM Regional Medical Centre", "lat": lat - 0.18, "lon": lon + 0.22,
            "resource_type": "medical_response", "capability_name": "SIM Medical Surge Team",
            "capabilities": ["emergency_care", "burn_stabilization", "patient_reception"],
            "availability": "available", "availability_score": 0.88, "readiness": 0.86, "capacity": 0.74, "suitability": 0.82,
            "capacity_detail": {"surge_patients": 20},
        },
        {
            "asset_type": "reception_centre", "name": "SIM Community Reception Centre", "lat": lat + 0.11, "lon": lon + 0.20,
            "resource_type": "evacuation_support", "capability_name": "SIM Reception and Shelter Team",
            "capabilities": ["registration", "temporary_shelter", "family_reunification"],
            "availability": "available", "availability_score": 0.93, "readiness": 0.84, "capacity": 0.76, "suitability": 0.88,
            "capacity_detail": {"people": 250},
        },
        {
            "asset_type": "emergency_facility", "name": "SIM Logistics Staging Area", "lat": lat + 0.31, "lon": lon - 0.14,
            "resource_type": "logistics", "capability_name": "SIM Heavy Equipment and Logistics Package",
            "capabilities": ["heavy_equipment", "fuel_support", "supply_staging"],
            "availability": "available", "availability_score": 0.86, "readiness": 0.80, "capacity": 0.92, "suitability": 0.83,
            "capacity_detail": {"dozers": 2, "water_tenders": 3},
        },
    ]


@router.post("", status_code=201)
def create_situation(payload: SituationCreate, session: Session = Depends(get_session)):
    situation = SituationRecord(**payload.model_dump(), status="active")
    session.add(situation)
    session.flush()
    _audit(session, situation.id, "created", "Situation created via API", {"domain": situation.domain})
    session.commit()
    session.refresh(situation)
    return situation


@router.post("/demo/wildfire", status_code=201)
def create_demo_wildfire(payload: DemoWildfireRequest, session: Session = Depends(get_session)):
    """Create a non-live Vancouver Island wildfire situation for end-to-end testing."""
    situation = SituationRecord(
        tenant_id=payload.tenant_id,
        domain="wildfire",
        status="active",
        title=payload.title,
        summary=(
            "SIMULATED TRAINING SCENARIO: A wildfire is developing in central Vancouver Island. "
            "Moderate-to-high winds are forecast and nearby communities, transportation corridors, "
            "health facilities and response resources should be assessed."
        ),
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_km=payload.radius_km,
        confidence=0.80,
        risk_score=0.68,
        urgency_score=0.72,
        severity="high",
        source_types=["demo", "simulated"],
        correlation_reasons=["training scenario", "AI orchestration validation"],
        evidence=[{
            "type": "simulation_notice",
            "source": "sitrep-demo",
            "statement": "This is synthetic training data and not a live emergency.",
            "confidence": 1.0,
        }],
        context={
            "simulation": True,
            "training_only": True,
            "forecast_trend": "worsening",
            "weather": {
                "wind_from_deg": 300,
                "wind_speed_kmh": 35,
                "forecast_note": "Simulated increasing winds for tool-orchestration testing",
            },
            "objectives": [
                "Assess exposed communities and critical facilities",
                "Assess road, rail and utility impacts",
                "Assess response-resource availability",
                "Generate and red-team courses of action",
            ],
        },
    )
    session.add(situation)
    session.flush()
    _audit(session, situation.id, "demo_created", "Synthetic wildfire training situation created", {"simulation": True, "training_only": True})
    session.commit()
    session.refresh(situation)
    return situation


@router.post("/{situation_id}/demo/resources", status_code=201)
def seed_demo_resources(situation_id: str, session: Session = Depends(get_session)):
    """Seed synthetic response resources around a simulated situation.

    Only permitted for situations explicitly marked training_only/simulation.
    Idempotent per situation through source_id naming.
    """
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise HTTPException(status_code=404, detail="Situation not found")
    context = situation.context or {}
    if not context.get("simulation") or not context.get("training_only"):
        raise HTTPException(status_code=400, detail="Demo resources may only be seeded into an explicit training simulation")
    if situation.latitude is None or situation.longitude is None:
        raise HTTPException(status_code=400, detail="Situation must have geolocation before demo resources can be seeded")

    created_assets: List[ExposureAsset] = []
    created_caps: List[ResponseResourceCapability] = []
    for idx, spec in enumerate(_demo_resource_specs(situation), start=1):
        source_id = f"demo-resource:{situation.id}:{idx}"
        existing = session.exec(
            select(ResponseResourceCapability)
            .where(ResponseResourceCapability.tenant_id == situation.tenant_id)
            .where(ResponseResourceCapability.source_id == source_id)
        ).first()
        if existing:
            continue
        asset = ExposureAsset(
            tenant_id=situation.tenant_id,
            asset_type=spec["asset_type"],
            name=spec["name"],
            latitude=spec["lat"],
            longitude=spec["lon"],
            criticality_score=0.72,
            vulnerability_score=0.35,
            source_system="sitrep-demo",
            source_id=f"demo-asset:{situation.id}:{idx}",
            properties={"simulation": True, "training_only": True, "situation_id": situation.id},
        )
        session.add(asset)
        session.flush()
        cap = ResponseResourceCapability(
            tenant_id=situation.tenant_id,
            exposure_asset_id=asset.id,
            resource_type=spec["resource_type"],
            name=spec["capability_name"],
            availability_status=spec["availability"],
            availability_score=spec["availability_score"],
            readiness_score=spec["readiness"],
            capacity_score=spec["capacity"],
            suitability_score=spec["suitability"],
            capabilities=spec["capabilities"],
            capacity=spec["capacity_detail"],
            suitability={"domains": ["wildfire"], "training_only": True},
            constraints=["SIMULATED RESOURCE - NOT FOR OPERATIONAL DISPATCH"],
            source_system="sitrep-demo",
            source_id=source_id,
            properties={"simulation": True, "training_only": True, "situation_id": situation.id},
        )
        session.add(cap)
        created_assets.append(asset)
        created_caps.append(cap)

    _audit(session, situation.id, "demo_resources_seeded", "Synthetic response resources seeded", {"created": len(created_caps), "training_only": True})
    session.commit()
    return {
        "situation_id": situation.id,
        "created_resource_count": len(created_caps),
        "created_asset_ids": [item.id for item in created_assets],
        "created_capability_ids": [item.id for item in created_caps],
        "training_only": True,
        "note": "All seeded resources are synthetic and must never be treated as dispatchable real-world assets.",
    }


@router.get("")
def list_situations(
    tenant_id: str = Query(default="default"),
    status: str = Query(default="active", description="Use 'all' to include every status"),
    domain: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    statement = select(SituationRecord).where(SituationRecord.tenant_id == tenant_id)
    if status.lower() != "all":
        statement = statement.where(SituationRecord.status == status)
    if domain:
        statement = statement.where(SituationRecord.domain == domain)
    statement = statement.order_by(SituationRecord.updated_at.desc()).limit(limit)
    return list(session.exec(statement).all())


@router.get("/{situation_id}")
def get_situation(situation_id: str, session: Session = Depends(get_session)):
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise HTTPException(status_code=404, detail="Situation not found")
    return situation


@router.patch("/{situation_id}")
def update_situation(situation_id: str, payload: SituationUpdate, session: Session = Depends(get_session)):
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise HTTPException(status_code=404, detail="Situation not found")
    changes = payload.model_dump(exclude_unset=True)
    note = changes.pop("note", "")
    changed_fields: Dict[str, Any] = {}
    for key, value in changes.items():
        if value is not None:
            setattr(situation, key, value)
            changed_fields[key] = value
    situation.updated_at = utcnow()
    session.add(situation)
    _audit(session, situation.id, "updated", note or "Situation updated via API", {"changed_fields": changed_fields})
    session.commit()
    session.refresh(situation)
    return situation


@router.post("/{situation_id}/close")
def close_situation(situation_id: str, payload: SituationStatusChange, session: Session = Depends(get_session)):
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise HTTPException(status_code=404, detail="Situation not found")
    situation.status = "closed"
    situation.updated_at = utcnow()
    session.add(situation)
    _audit(session, situation.id, "closed", payload.note or "Situation closed", {"actor": payload.actor})
    session.commit()
    session.refresh(situation)
    return situation


@router.post("/{situation_id}/reopen")
def reopen_situation(situation_id: str, payload: SituationStatusChange, session: Session = Depends(get_session)):
    situation = session.get(SituationRecord, situation_id)
    if not situation:
        raise HTTPException(status_code=404, detail="Situation not found")
    situation.status = "active"
    situation.updated_at = utcnow()
    session.add(situation)
    _audit(session, situation.id, "reopened", payload.note or "Situation reopened", {"actor": payload.actor})
    session.commit()
    session.refresh(situation)
    return situation


@router.post("/{situation_id}/enrich/exposure")
def enrich_exposure(situation_id: str, radius_km: float | None = Query(default=None, gt=0, le=500), session: Session = Depends(get_session)):
    try:
        return enrich_situation_exposure(session=session, situation_id=situation_id, radius_km=radius_km)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{situation_id}/enrich/infrastructure-impact")
def infrastructure_impact(
    situation_id: str,
    radius_km: float | None = Query(default=None, gt=0, le=500),
    max_depth: int = Query(default=4, ge=1, le=10),
    categories: str | None = Query(default=None, description="Optional comma-separated categories such as transport,electric"),
    session: Session = Depends(get_session),
):
    parsed_categories = [item.strip() for item in categories.split(",") if item.strip()] if categories else None
    try:
        return analyze_situation_infrastructure_impact(session=session, situation_id=situation_id, radius_km=radius_km, max_depth=max_depth, categories=parsed_categories)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{situation_id}/enrich/resources")
def resource_availability(
    situation_id: str,
    radius_km: float | None = Query(default=None, gt=0, le=500),
    tenant_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    try:
        return situation_resource_profile(session=session, situation_id=situation_id, radius_km=radius_km, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{situation_id}/enrich/wildfire-screen")
def wildfire_screen(
    situation_id: str,
    wind_from_deg: float = Query(ge=0, lt=360),
    wind_speed_kmh: float = Query(ge=0, le=250),
    horizon_hours: float = Query(default=6.0, gt=0, le=48),
    tenant_id: str = Query(default="default"),
    session: Session = Depends(get_session),
):
    try:
        return wildfire_exposure_screen(session=session, situation_id=situation_id, wind_from_deg=wind_from_deg, wind_speed_kmh=wind_speed_kmh, horizon_hours=horizon_hours, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{situation_id}/audit")
def get_situation_audit(situation_id: str, session: Session = Depends(get_session)):
    if not session.get(SituationRecord, situation_id):
        raise HTTPException(status_code=404, detail="Situation not found")
    statement = select(SituationAudit).where(SituationAudit.situation_id == situation_id).order_by(SituationAudit.created_at)
    return list(session.exec(statement).all())
