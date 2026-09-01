from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlmodel import Session, select

from app.models.exposure import ExposureAsset

DEFAULT_TIMEOUT_SECONDS = 30.0
ON_AFFES_QUERY = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open05/MapServer/21/query"
QC_FIRE_GEOJSON = "https://geoegl.msp.gouv.qc.ca/apis/wss/incendie.fcgi?service=wfs&version=1.1.0&request=getfeature&typename=MSP_CASERNE_PUBLIC&outputformat=geojson&srsName=epsg:4326"

EMERGENCY_COVERAGE: Dict[str, Dict[str, Any]] = {
    "ON": {"status": "supported", "source": "Ontario Fire, Aviation and Emergency Facility Point", "adapter": "on-affes"},
    "QC": {"status": "supported", "source": "Quebec public fire stations", "adapter": "qc-fire-stations"},
    "CA": {"status": "national_planning_context", "source": "Statistics Canada Open Database of Infrastructure v2", "note": "National planning-context source for airports and multiple infrastructure classes; prefer fresher jurisdiction feeds when available."},
}


class CanadaEmergencyImportError(RuntimeError):
    pass


def emergency_coverage() -> Dict[str, Dict[str, Any]]:
    return EMERGENCY_COVERAGE


def _upsert(session: Session, payload: Dict[str, Any]) -> bool:
    existing = session.exec(
        select(ExposureAsset)
        .where(ExposureAsset.tenant_id == payload["tenant_id"])
        .where(ExposureAsset.source_system == payload["source_system"])
        .where(ExposureAsset.source_id == payload["source_id"])
    ).first()
    if existing:
        for key in ("asset_type", "name", "latitude", "longitude", "population", "criticality_score", "vulnerability_score", "properties"):
            setattr(existing, key, payload[key])
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        return False
    session.add(ExposureAsset(**payload))
    return True


def _point_from_geometry(geometry: Dict[str, Any]) -> Optional[tuple[float, float]]:
    if geometry.get("type") == "Point":
        coords = geometry.get("coordinates") or []
        if len(coords) >= 2:
            return float(coords[1]), float(coords[0])
    if "x" in geometry and "y" in geometry:
        return float(geometry["y"]), float(geometry["x"])
    return None


def normalize_on_affes(feature: Dict[str, Any], tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    props = dict(feature.get("properties") or feature.get("attributes") or {})
    geometry = feature.get("geometry") or {}
    point = _point_from_geometry(geometry)
    if not point:
        return None
    lat, lon = point
    text = " ".join(str(v) for v in props.values() if v is not None).lower()
    if "airport" in text or "airbase" in text or "air base" in text:
        asset_type, criticality = "emergency_airbase", 0.92
    elif "heli" in text:
        asset_type, criticality = "heliport", 0.90
    elif "fire" in text:
        asset_type, criticality = "fire_station", 0.93
    else:
        asset_type, criticality = "emergency_facility", 0.88
    raw_id = feature.get("id") or props.get("OBJECTID") or props.get("OGF_ID") or f"{lat:.6f},{lon:.6f}"
    name = str(props.get("FACILITY_NAME") or props.get("NAME") or props.get("FACILITY_TYPE") or "Ontario emergency facility")
    return {"tenant_id": tenant_id, "asset_type": asset_type, "name": name, "latitude": lat, "longitude": lon, "population": None, "criticality_score": criticality, "vulnerability_score": 0.35, "source_system": "Ontario-AFFES", "source_id": f"ON-AFFES:{raw_id}", "properties": {"jurisdiction": "ON", "source_dataset": "Fire, Aviation and Emergency Facility Point", "public_attributes": props}}


def normalize_qc_fire(feature: Dict[str, Any], tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    props = dict(feature.get("properties") or {})
    point = _point_from_geometry(feature.get("geometry") or {})
    if not point:
        return None
    lat, lon = point
    raw_id = feature.get("id") or props.get("id") or props.get("ID") or props.get("OBJECTID") or f"{lat:.6f},{lon:.6f}"
    name = str(props.get("nom") or props.get("NOM") or props.get("name") or props.get("NAME") or "Quebec fire station")
    return {"tenant_id": tenant_id, "asset_type": "fire_station", "name": name, "latitude": lat, "longitude": lon, "population": None, "criticality_score": 0.93, "vulnerability_score": 0.30, "source_system": "QC-MSP-FireStations", "source_id": f"QC-FIRE:{raw_id}", "properties": {"jurisdiction": "QC", "source_dataset": "Quebec public fire stations", "public_attributes": props}}


async def _fetch_geojson(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers={"User-Agent": "SitRep/3.4 EmergencyImporter"})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CanadaEmergencyImportError(str(exc)) from exc


async def import_on_affes(session: Session, tenant_id: str = "default", bbox: Optional[str] = None, limit: int = 2000) -> Dict[str, Any]:
    params: Dict[str, Any] = {"f": "geojson", "where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326", "resultRecordCount": max(1, min(limit, 2000))}
    if bbox:
        parts = [float(v.strip()) for v in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
        params.update({"geometry": ",".join(str(v) for v in parts), "geometryType": "esriGeometryEnvelope", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"})
    payload = await _fetch_geojson(ON_AFFES_QUERY, params=params)
    features = list(payload.get("features") or [])
    created = updated = skipped = 0
    for feature in features:
        item = normalize_on_affes(feature, tenant_id)
        if not item:
            skipped += 1
            continue
        was_created = _upsert(session, item)
        created += int(was_created); updated += int(not was_created)
    session.commit()
    return {"source": "Ontario AFFES", "jurisdiction": "ON", "created": created, "updated": updated, "skipped": skipped, "fetched": len(features)}


async def import_qc_fire_stations(session: Session, tenant_id: str = "default", limit: int = 5000) -> Dict[str, Any]:
    payload = await _fetch_geojson(QC_FIRE_GEOJSON)
    features = list(payload.get("features") or [])[: max(1, min(limit, 5000))]
    created = updated = skipped = 0
    for feature in features:
        item = normalize_qc_fire(feature, tenant_id)
        if not item:
            skipped += 1
            continue
        was_created = _upsert(session, item)
        created += int(was_created); updated += int(not was_created)
    session.commit()
    return {"source": "Quebec public fire stations", "jurisdiction": "QC", "created": created, "updated": updated, "skipped": skipped, "fetched": len(features)}
