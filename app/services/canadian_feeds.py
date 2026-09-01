from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

ECCC_GEOMET_BASE = "https://api.weather.gc.ca"
ECCC_WEATHER_ALERTS_COLLECTION = "weather-alerts"
CWFIS_WFS_BASE = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/wfs"

DEFAULT_TIMEOUT_SECONDS = 12.0


class UpstreamFeedError(RuntimeError):
    pass


async def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers={"User-Agent": "SitRep/2.3 CanadianDataConnector"})
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


async def eccc_weather_alerts(
    bbox: Optional[str] = None,
    limit: int = 100,
    cql_filter: Optional[str] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"f": "json", "limit": max(1, min(limit, 1000))}
    if bbox:
        params["bbox"] = bbox
    if cql_filter:
        params["filter"] = cql_filter

    payload = await _get_json(
        f"{ECCC_GEOMET_BASE}/collections/{ECCC_WEATHER_ALERTS_COLLECTION}/items",
        params,
    )
    features = payload.get("features", [])
    return {
        "source": "Environment and Climate Change Canada / Weather Alerts",
        "source_url": f"{ECCC_GEOMET_BASE}/collections/{ECCC_WEATHER_ALERTS_COLLECTION}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "count": len(features),
        "features": features,
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


def _parse_source_datetime(properties: Dict[str, Any], keys: Tuple[str, ...]) -> datetime:
    for key in keys:
        value = properties.get(key)
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _flatten_coordinates(value: Any) -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            points.append((float(value[0]), float(value[1])))
        else:
            for item in value:
                points.extend(_flatten_coordinates(item))
    return points


def _geometry_centroid(geometry: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    points = _flatten_coordinates(geometry.get("coordinates") or [])
    if not points:
        return None, None
    longitude = sum(point[0] for point in points) / len(points)
    latitude = sum(point[1] for point in points) / len(points)
    return longitude, latitude


def cwfis_feature_to_observation(feature: Dict[str, Any], tenant_id: str = "default") -> Dict[str, Any]:
    geometry = feature.get("geometry") or {}
    properties = feature.get("properties") or {}
    longitude, latitude = _geometry_centroid(geometry)
    collected_at = _parse_source_datetime(
        properties,
        ("date", "datetime", "timestamp", "reporteddate", "lastupdate", "last_updated"),
    )

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


def eccc_alert_feature_to_observation(feature: Dict[str, Any], tenant_id: str = "default") -> Dict[str, Any]:
    geometry = feature.get("geometry") or {}
    properties = feature.get("properties") or {}
    longitude, latitude = _geometry_centroid(geometry)
    collected_at = _parse_source_datetime(
        properties,
        ("sent", "issued", "issue_datetime", "onset", "effective", "datetime", "timestamp"),
    )

    alert_type = properties.get("alert_type") or properties.get("event") or properties.get("event_en") or "weather alert"
    severity = properties.get("severity") or properties.get("risk_colour_en") or properties.get("urgency")

    return {
        "source_system": "ECCC-GeoMet",
        "source_type": "weather_alert",
        "object_type": f"weather hazard alert: {alert_type}",
        "collected_at": collected_at.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "confidence": 0.9,
        "features": {
            "feed_layer": ECCC_WEATHER_ALERTS_COLLECTION,
            "feature_id": feature.get("id"),
            "alert_type": alert_type,
            "severity": severity,
            "province": properties.get("province"),
            "properties": properties,
        },
        "raw_payload": feature,
        "classification_tag": "PUBLIC",
        "tenant_id": tenant_id,
    }


def normalize_cwfis_features(features: List[Dict[str, Any]], tenant_id: str = "default") -> List[Dict[str, Any]]:
    return [cwfis_feature_to_observation(feature, tenant_id=tenant_id) for feature in features]


def normalize_eccc_alert_features(features: List[Dict[str, Any]], tenant_id: str = "default") -> List[Dict[str, Any]]:
    return [eccc_alert_feature_to_observation(feature, tenant_id=tenant_id) for feature in features]
