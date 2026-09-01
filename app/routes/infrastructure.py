from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.infrastructure import InfrastructureFeature
from app.services.bc_infrastructure_import import (
    BCInfrastructureImportError,
    DEFAULT_VANCOUVER_ISLAND_BBOX,
    import_bc_infrastructure,
)
from app.services.canada_infrastructure_import import (
    CanadaInfrastructureImportError,
    import_nrn_major_roads,
    national_infrastructure_coverage,
)
from app.services.canada_rail_import import CanadaRailImportError, import_nrwn_rail
from app.services.canada_utility_import import CanadaUtilityImportError, import_nb_utilities, utility_coverage

router = APIRouter(prefix="/infrastructure", tags=["infrastructure"])

PUBLIC_SOURCE_CATALOG = {
    "canada-national-road-network": {"category": "transport", "subtype": "road", "publisher": "Statistics Canada / GeoBase", "licence": "Open Government Licence - Canada", "dataset": "National Road Network (NRN)", "coverage": "All provinces and territories"},
    "canada-national-railway-network": {"category": "transport", "subtype": "railway", "publisher": "Natural Resources Canada / Transport Canada / GeoBase", "licence": "Open Government Licence - Canada", "dataset": "National Railway Network (NRWN)", "coverage": "Provincial and territorial packages"},
    "bc-public-railway-track-line": {"category": "transport", "subtype": "railway", "publisher": "Government of British Columbia", "dataset": "Railway Track Line"},
    "bc-transmission-lines": {"category": "electric", "subtype": "transmission_line", "publisher": "Government of British Columbia", "dataset": "BC Transmission Lines", "note": "SitRep importer deliberately excludes voltage attributes from the operational copy."},
    "nb-utilities": {"category": "utility", "subtype": "mixed", "publisher": "Government of New Brunswick", "dataset": "Utilities", "coverage": "Major pipelines and power lines", "licence": "Open Government Licence - New Brunswick"},
}


class InfrastructureCreate(BaseModel):
    tenant_id: str = "default"
    category: str
    subtype: str = "general"
    name: str = "Unnamed feature"
    geometry: Dict[str, Any]
    centroid_latitude: Optional[float] = None
    centroid_longitude: Optional[float] = None
    criticality_score: float = PydanticField(default=0.5, ge=0.0, le=1.0)
    vulnerability_score: float = PydanticField(default=0.5, ge=0.0, le=1.0)
    source_system: str = "manual"
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    properties: Dict[str, Any] = {}


@router.get("/sources")
def infrastructure_sources():
    return PUBLIC_SOURCE_CATALOG


@router.get("/coverage/canada")
def canada_coverage():
    return national_infrastructure_coverage()


@router.get("/coverage/canada/utilities")
def canada_utility_coverage():
    return utility_coverage()


@router.post("/canada/roads/import")
async def import_canada_roads(jurisdiction: str = Query(..., min_length=2, max_length=2), bbox: Optional[str] = Query(default=None), tenant_id: str = Query(default="default"), limit: int = Query(default=2000, ge=1, le=2000), session: Session = Depends(get_session)):
    try:
        return await import_nrn_major_roads(session=session, jurisdiction=jurisdiction, tenant_id=tenant_id, bbox=bbox, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CanadaInfrastructureImportError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "Statistics Canada NRN", "error": str(exc)}) from exc


@router.post("/canada/rail/import")
async def import_canada_rail(jurisdiction: str = Query(..., min_length=2, max_length=2), tenant_id: str = Query(default="default"), limit: int = Query(default=5000, ge=1, le=5000), session: Session = Depends(get_session)):
    try:
        return await import_nrwn_rail(session=session, jurisdiction=jurisdiction, tenant_id=tenant_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CanadaRailImportError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "NRCan NRWN", "error": str(exc)}) from exc


@router.post("/canada/utilities/nb/import")
async def import_new_brunswick_utilities(tenant_id: str = Query(default="default"), limit: int = Query(default=5000, ge=1, le=5000), session: Session = Depends(get_session)):
    try:
        return await import_nb_utilities(session=session, tenant_id=tenant_id, limit=limit)
    except CanadaUtilityImportError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "Government of New Brunswick Utilities", "error": str(exc)}) from exc


@router.post("/bc/import")
async def import_bc_public_infrastructure(datasets: str = Query(default="roads,rail,transmission"), bbox: str = Query(default=DEFAULT_VANCOUVER_ISLAND_BBOX), tenant_id: str = Query(default="default"), limit_per_dataset: int = Query(default=1000, ge=1, le=1000), session: Session = Depends(get_session)):
    keys = [item.strip() for item in datasets.split(",") if item.strip()]
    try:
        return await import_bc_infrastructure(session=session, datasets=keys, tenant_id=tenant_id, bbox=bbox, limit_per_dataset=limit_per_dataset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BCInfrastructureImportError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "BC DataBC ArcGIS", "error": str(exc)}) from exc


@router.post("", status_code=201)
def create_infrastructure(payload: InfrastructureCreate, session: Session = Depends(get_session)):
    geometry_type = str(payload.geometry.get("type") or "Unknown")
    item = InfrastructureFeature(**payload.model_dump(), geometry_type=geometry_type, updated_at=datetime.now(timezone.utc))
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("")
def list_infrastructure(tenant_id: str = Query(default="default"), category: Optional[str] = Query(default=None), subtype: Optional[str] = Query(default=None), limit: int = Query(default=200, ge=1, le=2000), session: Session = Depends(get_session)):
    statement = select(InfrastructureFeature).where(InfrastructureFeature.tenant_id == tenant_id)
    if category:
        statement = statement.where(InfrastructureFeature.category == category)
    if subtype:
        statement = statement.where(InfrastructureFeature.subtype == subtype)
    statement = statement.order_by(InfrastructureFeature.updated_at.desc()).limit(limit)
    return list(session.exec(statement).all())


@router.get("/{feature_id}")
def get_infrastructure(feature_id: str, session: Session = Depends(get_session)):
    item = session.get(InfrastructureFeature, feature_id)
    if not item:
        raise HTTPException(status_code=404, detail="Infrastructure feature not found")
    return item
