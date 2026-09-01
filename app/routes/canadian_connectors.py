from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services.canadian_feeds import (
    UpstreamFeedError,
    cwfis_active_fires,
    eccc_collections,
    normalize_cwfis_features,
)
from app.services.feed_ingestion import classify_feed_change
from app.services.observation_pipeline import process_observation

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


@router.post("/cwfis/ingest")
async def ingest_cwfis_active_fires(
    bbox: str | None = Query(
        default=None,
        description="Optional WFS bbox as minLon,minLat,maxLon,maxLat,EPSG:4326",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    include_unchanged: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """Fetch and ingest current CWFIS active fires into the SitRep pipeline.

    Identical source features are skipped. New or changed fire records are
    persisted, fused, evaluated, and may generate a human-review decision proposal.
    """
    try:
        result = await cwfis_active_fires(bbox=bbox, limit=limit)
    except UpstreamFeedError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "NRCan CWFIS", "error": str(exc)}) from exc

    observations = normalize_cwfis_features(result["features"], tenant_id=tenant_id)
    processed = []
    skipped = []

    for observation in observations:
        change = await classify_feed_change(db, observation)
        feature_id = observation.get("features", {}).get("feature_id")

        if not change["is_changed"]:
            if include_unchanged:
                skipped.append({"feature_id": feature_id, "reason": "unchanged", "change": change})
            continue

        pipeline_result = await process_observation(db, observation)
        processed.append(
            {
                "feature_id": feature_id,
                "change": change,
                "observation_id": pipeline_result.get("observation_id"),
                "entity_id": pipeline_result.get("entity_id"),
                "decision_trigger": pipeline_result.get("decision_trigger"),
                "decision_proposal": pipeline_result.get("decision_proposal"),
            }
        )

    return {
        "status": "ok",
        "source": result["source"],
        "retrieved_at": result["retrieved_at"],
        "fetched": len(observations),
        "processed": len(processed),
        "unchanged": len(observations) - len(processed),
        "items": processed,
        "skipped": skipped,
        "freshness_note": result.get("freshness_note"),
        "human_authorization_required": True,
    }
