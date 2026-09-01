from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlmodel import Session, select

from app.models.infrastructure import InfrastructureFeature

NRN_MAPSERVER = "https://geo.statcan.gc.ca/geo_wa/rest/services/NRN-RRN/nrn_rrn/MapServer"
DEFAULT_TIMEOUT_SECONDS = 20.0

# Major-road layer ids from the bilingual NRN MapServer. These cover all provinces and territories.
NRN_MAJOR_ROAD_LAYERS: Dict[str, int] = {
    "AB": 62,
    "BC": 63,
    "MB": 64,
    "NB": 65,
    "NL": 66,
    "NS": 67,
    "NT": 68,
    "NU": 69,
    "ON": 70,
    "PE": 71,
    "QC": 72,
    "SK": 73,
    "YT": 74,
}

JURISDICTIONS = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "ON": "Ontario",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "YT": "Yukon",
}


class CanadaInfrastructureImportError(RuntimeError):
    pass


def _centroid(geometry: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    coords = geometry.get("coordinates") or []
    points: List[tuple[float, float]] = []

    def walk(value: Any) -> None:
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
                points.append((float(value[0]), float(value[1])))
            else:
                for item in value:
                    walk(item)

    walk(coords)
    if not points:
        return None, None
    lon = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return lat, lon


def _upsert(session: Session, payload: Dict[str, Any]) -> bool:
    existing = session.exec(
        select(InfrastructureFeature)
        .where(InfrastructureFeature.tenant_id == payload["tenant_id"])
        .where(InfrastructureFeature.source_system == payload["source_system"])
        .where(InfrastructureFeature.source_id == payload["source_id"])
    ).first()
    if existing:
        for key in (
            "category", "subtype", "name", "geometry_type", "geometry",
            "centroid_latitude", "centroid_longitude", "criticality_score",
            "vulnerability_score", "source_url", "properties"
        ):
            setattr(existing, key, payload[key])
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        return False
    session.add(InfrastructureFeature(**payload))
    return True


async def _fetch_major_roads(jurisdiction: str, bbox: Optional[str], limit: int) -> List[Dict[str, Any]]:
    code = jurisdiction.upper()
    if code not in NRN_MAJOR_ROAD_LAYERS:
        raise ValueError(f"Unsupported jurisdiction: {jurisdiction}")
    layer_id = NRN_MAJOR_ROAD_LAYERS[code]
    params: Dict[str, Any] = {
        "f": "geojson",
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": max(1, min(limit, 2000)),
    }
    if bbox:
        parts = [float(v.strip()) for v in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
        params.update({
            "geometry": ",".join(str(v) for v in parts),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        })
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(f"{NRN_MAPSERVER}/{layer_id}/query", params=params, headers={"User-Agent": "SitRep/2.9 CanadaInfrastructureImporter"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CanadaInfrastructureImportError(str(exc)) from exc
    if payload.get("error"):
        raise CanadaInfrastructureImportError(str(payload["error"]))
    return list(payload.get("features") or [])


def normalize_nrn_major_road(feature: Dict[str, Any], jurisdiction: str, tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    geometry = feature.get("geometry") or {}
    props = feature.get("properties") or {}
    if not geometry:
        return None
    lat, lon = _centroid(geometry)
    raw_id = feature.get("id") or props.get("OBJECTID") or props.get("NID") or props.get("nid")
    source_id = f"NRN:{jurisdiction.upper()}:{raw_id}"
    route_name = props.get("ROUTENAME1") or props.get("ROUTENAME") or props.get("STREETNAME") or props.get("ROADCLASS")
    name = str(route_name or f"{JURISDICTIONS[jurisdiction.upper()]} major road")
    return {
        "tenant_id": tenant_id,
        "category": "transport",
        "subtype": "road",
        "name": name,
        "geometry_type": str(geometry.get("type") or "Unknown"),
        "geometry": geometry,
        "centroid_latitude": lat,
        "centroid_longitude": lon,
        "criticality_score": 0.75,
        "vulnerability_score": 0.45,
        "source_system": "StatCan-NRN",
        "source_id": source_id,
        "source_url": NRN_MAPSERVER,
        "properties": {"jurisdiction": jurisdiction.upper(), "nrn": props},
    }


async def import_nrn_major_roads(
    session: Session,
    jurisdiction: str,
    tenant_id: str = "default",
    bbox: Optional[str] = None,
    limit: int = 2000,
) -> Dict[str, Any]:
    features = await _fetch_major_roads(jurisdiction, bbox=bbox, limit=limit)
    created = updated = skipped = 0
    for feature in features:
        payload = normalize_nrn_major_road(feature, jurisdiction=jurisdiction, tenant_id=tenant_id)
        if not payload:
            skipped += 1
            continue
        was_created = _upsert(session, payload)
        created += int(was_created)
        updated += int(not was_created)
    session.commit()
    return {
        "source": "Statistics Canada / National Road Network",
        "jurisdiction": jurisdiction.upper(),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "fetched": len(features),
    }


def national_infrastructure_coverage() -> Dict[str, Any]:
    return {
        code: {
            "name": name,
            "roads": {"status": "supported", "source": "StatCan National Road Network"},
            "rail": {"status": "available_source", "source": "NRCan National Railway Network", "ingestion": "adapter/download integration pending"},
            "utilities": {"status": "jurisdiction_adapter_required"},
        }
        for code, name in JURISDICTIONS.items()
    }
