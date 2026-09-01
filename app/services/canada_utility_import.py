from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlmodel import Session, select

from app.models.infrastructure import InfrastructureFeature

DEFAULT_TIMEOUT_SECONDS = 30.0
NB_UTILITIES_GEOJSON = "https://gnb.socrata.com/api/geospatial/y3vu-vr3p?method=export&format=GeoJSON"
ON_UTILITY_LINE_QUERY = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open05/MapServer/11/query"

UTILITY_COVERAGE: Dict[str, Dict[str, Any]] = {
    "BC": {"status": "supported", "source": "Government of British Columbia public transmission lines", "adapter": "bc-transmission"},
    "NB": {"status": "supported", "source": "Government of New Brunswick Utilities", "adapter": "nb-utilities"},
    "ON": {"status": "supported_planning_context", "source": "Ontario Utility Line / Land Information Ontario", "adapter": "on-utility-line", "note": "Open linework covers power, water, communications and heating-fuel utilities. Source metadata indicates historical line data; store and expose freshness metadata and do not treat as current operational topology."},
    "QC": {"status": "partial_public", "source": "Données Québec / municipal transmission-line datasets", "adapter": "adapter_pending", "note": "No single province-wide open transmission layer confirmed; municipal coverage exists."},
    "AB": {"status": "source_validation_required", "adapter": "pending"},
    "MB": {"status": "source_validation_required", "adapter": "pending"},
    "NL": {"status": "source_validation_required", "adapter": "pending"},
    "NS": {"status": "source_validation_required", "adapter": "pending"},
    "NT": {"status": "source_validation_required", "adapter": "pending"},
    "NU": {"status": "source_validation_required", "adapter": "pending"},
    "PE": {"status": "source_validation_required", "adapter": "pending"},
    "SK": {"status": "source_validation_required", "adapter": "pending"},
    "YT": {"status": "source_validation_required", "adapter": "pending"},
}


class CanadaUtilityImportError(RuntimeError):
    pass


def utility_coverage() -> Dict[str, Dict[str, Any]]:
    return UTILITY_COVERAGE


def _centroid(geometry: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    points: List[tuple[float, float]] = []
    def walk(value: Any) -> None:
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
                points.append((float(value[0]), float(value[1])))
            else:
                for item in value:
                    walk(item)
    walk(geometry.get("coordinates") or [])
    if not points:
        return None, None
    return sum(p[1] for p in points) / len(points), sum(p[0] for p in points) / len(points)


def _upsert(session: Session, payload: Dict[str, Any]) -> bool:
    existing = session.exec(
        select(InfrastructureFeature)
        .where(InfrastructureFeature.tenant_id == payload["tenant_id"])
        .where(InfrastructureFeature.source_system == payload["source_system"])
        .where(InfrastructureFeature.source_id == payload["source_id"])
    ).first()
    if existing:
        for key in ("category", "subtype", "name", "geometry_type", "geometry", "centroid_latitude", "centroid_longitude", "criticality_score", "vulnerability_score", "source_url", "properties"):
            setattr(existing, key, payload[key])
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        return False
    session.add(InfrastructureFeature(**payload))
    return True


def _classify_utility_text(text: str) -> tuple[str, str, float]:
    lowered = text.lower()
    if any(term in lowered for term in ("hydro", "power", "electric", "transmission")):
        return "electric", "transmission_line", 0.88
    if any(term in lowered for term in ("communication", "telecom", "fibre", "fiber")):
        return "telecom", "communications_line", 0.78
    if "water" in lowered:
        return "water", "water_pipeline", 0.80
    if any(term in lowered for term in ("natural gas", "gas", "fuel", "pipeline")):
        return "fuel", "pipeline", 0.82
    return "utility", "utility_line", 0.65


def normalize_nb_utility(feature: Dict[str, Any], tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    geometry = feature.get("geometry") or {}
    if not geometry:
        return None
    props = dict(feature.get("properties") or {})
    text = " ".join(str(v) for v in props.values() if v is not None)
    category, subtype, criticality = _classify_utility_text(text)
    lat, lon = _centroid(geometry)
    raw_id = feature.get("id") or props.get("OBJECTID") or props.get("objectid") or props.get("id")
    if raw_id is None:
        raw_id = f"{geometry.get('type')}:{hash(str(geometry))}"
    name = str(props.get("name") or props.get("NAME") or props.get("type") or props.get("TYPE") or f"New Brunswick {subtype}")
    return {
        "tenant_id": tenant_id,
        "category": category,
        "subtype": subtype,
        "name": name,
        "geometry_type": str(geometry.get("type") or "Unknown"),
        "geometry": geometry,
        "centroid_latitude": lat,
        "centroid_longitude": lon,
        "criticality_score": criticality,
        "vulnerability_score": 0.50,
        "source_system": "NB-OpenData-Utilities",
        "source_id": f"NB-UTIL:{raw_id}",
        "source_url": NB_UTILITIES_GEOJSON,
        "properties": {"jurisdiction": "NB", "source_dataset": "Government of New Brunswick Utilities", "public_attributes": props},
    }


def normalize_on_utility(feature: Dict[str, Any], tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    geometry = feature.get("geometry") or {}
    if not geometry:
        return None
    props = dict(feature.get("properties") or {})
    text = " ".join(str(v) for v in props.values() if v is not None)
    category, subtype, criticality = _classify_utility_text(text)
    lat, lon = _centroid(geometry)
    raw_id = feature.get("id") or props.get("OBJECTID") or props.get("objectid") or props.get("OGF_ID") or props.get("ogf_id")
    if raw_id is None:
        raw_id = f"{geometry.get('type')}:{hash(str(geometry))}"
    label = props.get("UTILITY_LINE_TYPE") or props.get("UTILITY_TYPE") or props.get("FEATURE_TYPE") or props.get("TYPE") or props.get("DESCRIPTION")
    return {
        "tenant_id": tenant_id,
        "category": category,
        "subtype": subtype,
        "name": str(label or f"Ontario {subtype}"),
        "geometry_type": str(geometry.get("type") or "Unknown"),
        "geometry": geometry,
        "centroid_latitude": lat,
        "centroid_longitude": lon,
        "criticality_score": criticality,
        "vulnerability_score": 0.50,
        "source_system": "Ontario-LIO-UtilityLine",
        "source_id": f"ON-UTIL:{raw_id}",
        "source_url": ON_UTILITY_LINE_QUERY,
        "properties": {
            "jurisdiction": "ON",
            "source_dataset": "Ontario Utility Line",
            "planning_context_only": True,
            "source_last_updated": "2013-07-02",
            "source_data_range_end": "2008-06-12",
            "freshness_warning": "Historical/open planning context; not authoritative current operational topology.",
            "public_attributes": props,
        },
    }


async def import_nb_utilities(session: Session, tenant_id: str = "default", limit: int = 5000) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(NB_UTILITIES_GEOJSON, headers={"User-Agent": "SitRep/3.2 UtilityImporter"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CanadaUtilityImportError(str(exc)) from exc

    features = list(payload.get("features") or [])[: max(1, min(limit, 5000))]
    created = updated = skipped = 0
    by_subtype: Dict[str, int] = {}
    for feature in features:
        item = normalize_nb_utility(feature, tenant_id=tenant_id)
        if not item:
            skipped += 1
            continue
        was_created = _upsert(session, item)
        created += int(was_created)
        updated += int(not was_created)
        by_subtype[item["subtype"]] = by_subtype.get(item["subtype"], 0) + 1
    session.commit()
    return {"source": "Government of New Brunswick Utilities", "jurisdiction": "NB", "created": created, "updated": updated, "skipped": skipped, "fetched": len(features), "by_subtype": by_subtype}


async def import_on_utilities(session: Session, tenant_id: str = "default", bbox: Optional[str] = None, limit: int = 5000) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "f": "geojson",
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": max(1, min(limit, 5000)),
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
            response = await client.get(ON_UTILITY_LINE_QUERY, params=params, headers={"User-Agent": "SitRep/3.2 UtilityImporter"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CanadaUtilityImportError(str(exc)) from exc
    if payload.get("error"):
        raise CanadaUtilityImportError(str(payload["error"]))

    features = list(payload.get("features") or [])
    created = updated = skipped = 0
    by_subtype: Dict[str, int] = {}
    for feature in features:
        item = normalize_on_utility(feature, tenant_id=tenant_id)
        if not item:
            skipped += 1
            continue
        was_created = _upsert(session, item)
        created += int(was_created)
        updated += int(not was_created)
        by_subtype[item["subtype"]] = by_subtype.get(item["subtype"], 0) + 1
    session.commit()
    return {
        "source": "Ontario Utility Line / Land Information Ontario",
        "jurisdiction": "ON",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "fetched": len(features),
        "by_subtype": by_subtype,
        "planning_context_only": True,
        "freshness_warning": "Source linework is historical; do not use as current operational grid topology without an authorized/current source.",
    }
