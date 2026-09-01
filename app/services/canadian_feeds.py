from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

ECCC_GEOMET_BASE = "https://api.weather.gc.ca"
CWFIS_WFS_BASE = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/wfs"

DEFAULT_TIMEOUT_SECONDS = 12.0


class UpstreamFeedError(RuntimeError):
    pass


async def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers={"User-Agent": "SitRep/2.2 CanadianDataConnector"})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpstreamFeedError(str(exc)) from exc


async def eccc_collections(limit: int = 100) -> Dict[str, Any]:
    payload = await _get_json(f"{ECCC_GEOMET_BASE}/collections", {"f": "json"})
    collections = payload.get("collections", [])[: max(1, min(limit, 500))]
    return {
        "source": "Environment and Climate Change Canada / MSC GeoMet",
        "source_url": ECCC_GEOMET_BASE,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "count": len(collections),
        "collections": collections,
    }


async def cwfis_active_fires(
    bbox: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "public:activefires_current",
        "outputFormat": "application/json",
        "count": max(1, min(limit, 1000)),
        "srsName": "EPSG:4326",
    }
    if bbox:
        params["bbox"] = bbox

    payload = await _get_json(CWFIS_WFS_BASE, params)
    features = payload.get("features", [])
    return {
        "source": "Natural Resources Canada / Canadian Wildland Fire Information System",
        "source_url": CWFIS_WFS_BASE,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "count": len(features),
        "features": features,
        "freshness_note": "CWFIS is a national aggregation. Provincial, territorial, or Parks Canada agencies may have more current operational information.",
    }


def cwfis_feature_to_observation(feature: Dict[str, Any], tenant_id: str = "default") -> Dict[str, Any]:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    properties = feature.get("properties") or {}

    longitude: Optional[float] = None
    latitude: Optional[float] = None
    if geometry.get("type") == "Point" and len(coordinates) >= 2:
        longitude = float(coordinates[0])
        latitude = float(coordinates[1])

    source_timestamp = None
    for key in ("date", "datetime", "timestamp", "reporteddate", "lastupdate", "last_updated"):
        if properties.get(key):
            source_timestamp = properties[key]
            break

    collected_at = datetime.now(timezone.utc)
    if source_timestamp:
        try:
            parsed = datetime.fromisoformat(str(source_timestamp).replace("Z", "+00:00"))
            collected_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return {
        "source_system": "NRCan-CWFIS",
        "source_type": "active_fire",
        "object_type": "wildfire active fire",
        "collected_at": collected_at.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "confidence": 0.75,
        "features": {
            "feed_layer": "public:activefires_current",
            "feature_id": feature.get("id"),
            "properties": properties,
        },
        "raw_payload": feature,
        "classification_tag": "PUBLIC",
        "tenant_id": tenant_id,
    }


def normalize_cwfis_features(features: List[Dict[str, Any]], tenant_id: str = "default") -> List[Dict[str, Any]]:
    return [cwfis_feature_to_observation(feature, tenant_id=tenant_id) for feature in features]
