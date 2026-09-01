from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.models.db import get_session
from app.services.canadian_exposure_feeds import (
    ExposureFeedError,
    import_ised_bc_placenames,
    import_odhf_bc,
)
from app.services.statcan_population import PopulationFeedError, enrich_bc_community_population

router = APIRouter(prefix="/api/v1/connectors/canada/exposures", tags=["canadian-exposures"])


@router.post("/bc/health-facilities/import")
async def import_bc_health_facilities(
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    limit: int = Query(default=2000, ge=1, le=5000),
    session: Session = Depends(get_session),
):
    try:
        return await import_odhf_bc(session=session, tenant_id=tenant_id, limit=limit)
    except ExposureFeedError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "Statistics Canada ODHF", "error": str(exc)}) from exc


@router.post("/bc/communities/import")
async def import_bc_communities(
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    limit: int = Query(default=10000, ge=1, le=50000),
    session: Session = Depends(get_session),
):
    try:
        return await import_ised_bc_placenames(session=session, tenant_id=tenant_id, limit=limit)
    except ExposureFeedError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "ISED Geolocated Placenames", "error": str(exc)}) from exc


@router.post("/bc/population/enrich")
async def enrich_bc_population(
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    session: Session = Depends(get_session),
):
    try:
        return await enrich_bc_community_population(session=session, tenant_id=tenant_id)
    except PopulationFeedError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "Statistics Canada 2021 population centres", "error": str(exc)}) from exc
