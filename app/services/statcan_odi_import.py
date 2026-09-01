from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlmodel import Session, select

from app.models.exposure import ExposureAsset
from app.models.infrastructure import InfrastructureFeature

ARCGIS_ITEM_ID = "1edc05b2e59c41b08440111efedda62f"
ARCGIS_ITEM_URL = f"https://www.arcgis.com/sharing/rest/content/items/{ARCGIS_ITEM_ID}"
DEFAULT_TIMEOUT_SECONDS = 30.0

# Canonical SitRep categories -> likely ODI layer-name fragments.
ODI_TYPES: Dict[str, Dict[str, Any]] = {
    "airports": {
        "match": ["airport"],
        "target": "exposure",
        "asset_type": "airport",
        "criticality": 0.88,
        "vulnerability": 0.35,
    },
    "electric_grid": {
        "match": ["electric grid", "electrical grid"],
        "target": "infrastructure",
        "category": "electric",
        "subtype": "electric_grid",
        "criticality": 0.90,
        "vulnerability": 0.45,
    },
    "telecommunications": {
        "match": ["telecommunication"],
        "target": "infrastructure",
        "category": "telecom",
        "subtype": "telecommunications",
        "criticality": 0.86,
        "vulnerability": 0.50,
    },
    "potable_water": {
        "match": ["potable water"],
        "target": "infrastructure",
        "category": "water",
        "subtype": "potable_water",
        "criticality": 0.88,
        "vulnerability": 0.48,
    },
}


class ODIImportError(RuntimeError):
    pass


def odi_catalog() -> Dict[str, Any]:
    return {
        "source": "Statistics Canada Open Database of Infrastructure v2 / Esri Canada feature service",
        "item_id": ARCGIS_ITEM_ID,
        "version": "2.0",
        "release_date": "2024-11-13",
        "planning_context": True,
        "types": ODI_TYPES,
        "note": "ODI is harmonized public/open infrastructure context. Prefer fresher authoritative jurisdiction/authorized feeds when available.",
    }


def _centroid(geometry: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    points: List[tuple[float, float]] = []

    def walk(value: Any) -> None:
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
                points.append((float(value[0]), float(value[1])))
            else:
                for child in value:
                    walk(child)

    walk(geometry.get("coordinates") or [])
    if not points:
        return None, None
    return sum(p[1] for p in points) / len(points), sum(p[0] for p in points) / len(points)


def _prop(props: Dict[str, Any], *names: str) -> Any:
    lower = {str(k).lower(): v for k, v in props.items()}
    for name in names:
        value = lower.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _jurisdiction_matches(props: Dict[str, Any], jurisdiction: Optional[str]) -> bool:
    if not jurisdiction:
        return True
    code = jurisdiction.upper()
    text = " ".join(str(v) for v in props.values() if v is not None).upper()
    province_names = {
        "AB": "ALBERTA", "BC": "BRITISH COLUMBIA", "MB": "MANITOBA", "NB": "NEW BRUNSWICK",
        "NL": "NEWFOUNDLAND", "NS": "NOVA SCOTIA", "NT": "NORTHWEST TERRITORIES",
        "NU": "NUNAVUT", "ON": "ONTARIO", "PE": "PRINCE EDWARD ISLAND", "QC": "QUEBEC",
        "SK": "SASKATCHEWAN", "YT": "YUKON",
    }
    return code in text or province_names.get(code, code) in text


async def _service_url_and_layers() -> tuple[str, List[Dict[str, Any]]]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            item = await client.get(ARCGIS_ITEM_URL, params={"f": "json"}, headers={"User-Agent": "SitRep/3.5 ODIImporter"})
            item.raise_for_status()
            payload = item.json()
            service_url = payload.get("url")
            if not service_url:
                raise ODIImportError("ODI ArcGIS item did not expose a service URL")
            meta = await client.get(service_url, params={"f": "json"}, headers={"User-Agent": "SitRep/3.5 ODIImporter"})
            meta.raise_for_status()
            service = meta.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ODIImportError(str(exc)) from exc
    layers = list(service.get("layers") or []) + list(service.get("tables") or [])
    return str(service_url).rstrip("/"), layers


def _find_layer(layers: List[Dict[str, Any]], odi_type: str) -> Dict[str, Any]:
    config = ODI_TYPES.get(odi_type)
    if not config:
        raise ValueError(f"Unsupported ODI type: {odi_type}")
    candidates: List[Dict[str, Any]] = []
    for layer in layers:
        name = str(layer.get("name") or "").lower()
        if any(term in name for term in config["match"]):
            candidates.append(layer)
    if not candidates:
        raise ODIImportError(f"Could not discover ODI layer for {odi_type}")
    candidates.sort(key=lambda item: len(str(item.get("name") or "")))
    return candidates[0]


async def _fetch_features(odi_type: str, bbox: Optional[str], limit: int) -> tuple[str, List[Dict[str, Any]]]:
    service_url, layers = await _service_url_and_layers()
    layer = _find_layer(layers, odi_type)
    layer_url = f"{service_url}/{layer['id']}"
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
            response = await client.get(f"{layer_url}/query", params=params, headers={"User-Agent": "SitRep/3.5 ODIImporter"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ODIImportError(str(exc)) from exc
    if payload.get("error"):
        raise ODIImportError(str(payload["error"]))
    return layer_url, list(payload.get("features") or [])


def _common_properties(props: Dict[str, Any], odi_type: str, layer_url: str) -> Dict[str, Any]:
    return {
        "odi_type": odi_type,
        "planning_context_only": True,
        "odi_version": "2.0",
        "odi_release_date": "2024-11-13",
        "source_collection_window": "2023-10 to 2024-06",
        "freshness_warning": "ODI is harmonized planning context; source reference periods vary. Prefer fresher authoritative feeds when available.",
        "source_layer_url": layer_url,
        "public_attributes": props,
    }


def _source_id(feature: Dict[str, Any], props: Dict[str, Any], odi_type: str) -> str:
    raw = feature.get("id") or _prop(props, "unique_id", "uid", "objectid", "source_id", "id")
    if raw is None:
        raw = abs(hash(str((feature.get("geometry"), sorted((str(k), str(v)) for k, v in props.items())))))
    return f"ODI:{odi_type}:{raw}"


def normalize_odi_feature(feature: Dict[str, Any], odi_type: str, layer_url: str, tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    config = ODI_TYPES[odi_type]
    geometry = feature.get("geometry") or {}
    props = dict(feature.get("properties") or {})
    if not geometry:
        return None
    lat, lon = _centroid(geometry)
    if lat is None or lon is None:
        # Exposure assets require a representative point. Infrastructure line/polygon
        # features also benefit from a centroid for proximity screening.
        return None
    name = str(_prop(props, "name", "infrastructure_name", "facility_name", "airport_name") or f"ODI {odi_type.replace('_', ' ')}")
    common = _common_properties(props, odi_type, layer_url)
    sid = _source_id(feature, props, odi_type)
    if config["target"] == "exposure":
        return {
            "target": "exposure",
            "payload": {
                "tenant_id": tenant_id,
                "asset_type": config["asset_type"],
                "name": name,
                "latitude": lat,
                "longitude": lon,
                "population": None,
                "criticality_score": config["criticality"],
                "vulnerability_score": config["vulnerability"],
                "source_system": "StatCan-ODI",
                "source_id": sid,
                "properties": common,
            },
        }
    return {
        "target": "infrastructure",
        "payload": {
            "tenant_id": tenant_id,
            "category": config["category"],
            "subtype": config["subtype"],
            "name": name,
            "geometry_type": str(geometry.get("type") or "Unknown"),
            "geometry": geometry,
            "centroid_latitude": lat,
            "centroid_longitude": lon,
            "criticality_score": config["criticality"],
            "vulnerability_score": config["vulnerability"],
            "source_system": "StatCan-ODI",
            "source_id": sid,
            "source_url": layer_url,
            "properties": common,
        },
    }


def _upsert_exposure(session: Session, payload: Dict[str, Any]) -> bool:
    existing = session.exec(
        select(ExposureAsset)
        .where(ExposureAsset.tenant_id == payload["tenant_id"])
        .where(ExposureAsset.source_system == payload["source_system"])
        .where(ExposureAsset.source_id == payload["source_id"])
    ).first()
    if existing:
        for key, value in payload.items():
            if key not in {"tenant_id", "source_system", "source_id"}:
                setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        return False
    session.add(ExposureAsset(**payload))
    return True


def _upsert_infrastructure(session: Session, payload: Dict[str, Any]) -> bool:
    existing = session.exec(
        select(InfrastructureFeature)
        .where(InfrastructureFeature.tenant_id == payload["tenant_id"])
        .where(InfrastructureFeature.source_system == payload["source_system"])
        .where(InfrastructureFeature.source_id == payload["source_id"])
    ).first()
    if existing:
        for key, value in payload.items():
            if key not in {"tenant_id", "source_system", "source_id"}:
                setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        return False
    session.add(InfrastructureFeature(**payload))
    return True


async def import_odi(
    session: Session,
    odi_type: str,
    tenant_id: str = "default",
    jurisdiction: Optional[str] = None,
    bbox: Optional[str] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    if odi_type not in ODI_TYPES:
        raise ValueError(f"Unsupported ODI type: {odi_type}")
    layer_url, features = await _fetch_features(odi_type, bbox=bbox, limit=limit)
    created = updated = skipped = filtered = 0
    for feature in features:
        props = dict(feature.get("properties") or {})
        if jurisdiction and not _jurisdiction_matches(props, jurisdiction):
            filtered += 1
            continue
        normalized = normalize_odi_feature(feature, odi_type=odi_type, layer_url=layer_url, tenant_id=tenant_id)
        if not normalized:
            skipped += 1
            continue
        if normalized["target"] == "exposure":
            was_created = _upsert_exposure(session, normalized["payload"])
        else:
            was_created = _upsert_infrastructure(session, normalized["payload"])
        created += int(was_created)
        updated += int(not was_created)
    session.commit()
    return {
        "source": "Statistics Canada Open Database of Infrastructure v2",
        "odi_type": odi_type,
        "jurisdiction": jurisdiction.upper() if jurisdiction else None,
        "layer_url": layer_url,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "filtered_out": filtered,
        "fetched": len(features),
        "planning_context_only": True,
    }
