from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.canadian_feeds import (
    UpstreamFeedError,
    cwfis_active_fires,
    eccc_collections,
    normalize_cwfis_features,
)

router = APIRouter(prefix="/api/v1/connectors/canada", tags=["canadian-connectors"])


@router.get("/status")
async def connector_status():
    status = {
        "eccc_geomet": {"ok": False, "detail": None},
        "nrcan_cwfis": {"ok": False, "detail": None},
    }

    try:
        collections = await eccc_collections(limit=1)
        status["eccc_geomet"] = {"ok": True, "detail": f"{collections['count']} collection sampled"}
    except UpstreamFeedError as exc:
        status["eccc_geomet"]["detail"] = str(exc)

    try:
        fires = await cwfis_active_fires(limit=1)
        status["nrcan_cwfis"] = {"ok": True, "detail": f"{fires['count']} active-fire feature sampled"}
    except UpstreamFeedError as exc:
        status["nrcan_cwfis"]["detail"] = str(exc)

    return status


@router.get("/eccc/collections")
async def list_eccc_collections(limit: int = Query(default=100, ge=1, le=500)):
    try:
        return await eccc_collections(limit=limit)
    except UpstreamFeedError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "ECCC GeoMet", "error": str(exc)}) from exc


@router.get("/cwfis/active-fires")
async def list_cwfis_active_fires(
    bbox: str | None = Query(
        default=None,
        description="Optional WFS bbox as minLon,minLat,maxLon,maxLat,EPSG:4326",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    normalized: bool = Query(default=True),
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
):
    try:
        result = await cwfis_active_fires(bbox=bbox, limit=limit)
    except UpstreamFeedError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "NRCan CWFIS", "error": str(exc)}) from exc

    if normalized:
        result["observations"] = normalize_cwfis_features(result["features"], tenant_id=tenant_id)
    return result
