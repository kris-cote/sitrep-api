from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
from sqlmodel import Session, select

from app.models.infrastructure import InfrastructureFeature

BC_BASEMAPPING = "https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_basemapping/MapServer"
DEFAULT_VANCOUVER_ISLAND_BBOX = "-128.8,48.1,-123.0,51.7"
DEFAULT_TIMEOUT_SECONDS = 20.0

DATASETS: Dict[str, Dict[str, Any]] = {
    "roads": {
        "layer": 68,
        "category": "transport",
        "subtype": "road",
        "name_fields": ("STREET_NAME", "ROAD_NAME", "ROUTE_NAME", "FULL_NAME"),
        "source_dataset": "Digital Road Atlas (DRA) - Master Partially-Attributed Roads",
        "criticality": 0.80,
        "vulnerability": 0.55,
    },
    "rail": {
        "layer": 44,
        "category": "transport",
        "subtype": "railway",
        "name_fields": ("TRACK_NAME", "RAILWAY_NAME", "OWNER", "OPERATOR"),
        "source_dataset": "Railway Track Line",
        "criticality": 0.78,
        "vulnerability": 0.60,
    },
    "transmission": {
        "layer": 77,
        "category": "electric",
        "subtype": "transmission_line",
        "name_fields": ("CIRCUIT_NAME", "CIRCUIT_DESCRIPTION", "OWNER"),
        "source_dataset": "BC Transmission Lines",
        "criticality": 0.90,
        "vulnerability": 0.70,
        "redact_fields": {"VOLTAGE"},
    },
}


class BCInfrastructureImportError(RuntimeError):
    pass


def _first(props: Dict[str, Any], fields: Iterable[str]) -> Optional[str]:
    for field in fields:
        value = props.get(field)
        if value not in (None, ""):
            return str(value)
    return None


def _flatten(coords: Any) -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []
    if isinstance(coords, (list, tuple)):
        if len(coords) >= 2 and isinstance(coords[0], (int, float)) and isinstance(coords[1], (int, float)):
            points.append((float(coords[0]), float(coords[1])))
        else:
            for item in coords:
                points.extend(_flatten(item))
    return points


def _centroid(geometry: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    points = _flatten(geometry.get("coordinates") or [])
    if not points:
        return None, None
    lon = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return lat, lon


async def _fetch_layer(dataset_key: str, bbox: str, limit: int) -> List[Dict[str, Any]]:
    dataset = DATASETS[dataset_key]
    url = f"{BC_BASEMAPPING}/{dataset['layer']}/query"
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometry": bbox,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "f": "geojson",
        "resultRecordCount": max(1, min(limit, 1000)),
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers={"User-Agent": "SitRep/2.8 BCInfrastructureImporter"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BCInfrastructureImportError(str(exc)) from exc
    return list(payload.get("features") or [])


def normalize_bc_infrastructure(dataset_key: str, feature: Dict[str, Any], tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    dataset = DATASETS[dataset_key]
    geometry = feature.get("geometry") or {}
    props = dict(feature.get("properties") or {})
    lat, lon = _centroid(geometry)
    if lat is None or lon is None:
        return None

    for field in dataset.get("redact_fields", set()):
        props.pop(field, None)
        props.pop(field.lower(), None)

    raw_id = feature.get("id") or props.get("OBJECTID") or props.get("objectid")
    source_id = f"{dataset_key}:{raw_id or f'{lat:.6f},{lon:.6f}'}"
    name = _first(props, dataset["name_fields"]) or f"{dataset['subtype']} {source_id}"
    source_url = f"{BC_BASEMAPPING}/{dataset['layer']}"

    return {
        "tenant_id": tenant_id,
        "category": dataset["category"],
        "subtype": dataset["subtype"],
        "name": name,
        "geometry_type": str(geometry.get("type") or "Unknown"),
        "geometry": geometry,
        "centroid_latitude": lat,
        "centroid_longitude": lon,
        "criticality_score": float(dataset["criticality"]),
        "vulnerability_score": float(dataset["vulnerability"]),
        "source_system": "BC-DataBC-ArcGIS",
        "source_id": source_id,
        "source_url": source_url,
        "properties": {
            "source_dataset": dataset["source_dataset"],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "attributes": props,
        },
    }


def _upsert(session: Session, payload: Dict[str, Any]) -> bool:
    existing = session.exec(
        select(InfrastructureFeature)
        .where(InfrastructureFeature.tenant_id == payload["tenant_id"])
        .where(InfrastructureFeature.source_system == payload["source_system"])
        .where(InfrastructureFeature.source_id == payload["source_id"])
    ).first()
    if existing:
        for key, value in payload.items():
            if key != "tenant_id":
                setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        return False
    session.add(InfrastructureFeature(**payload))
    return True


async def import_bc_infrastructure(
    session: Session,
    datasets: List[str],
    tenant_id: str = "default",
    bbox: str = DEFAULT_VANCOUVER_ISLAND_BBOX,
    limit_per_dataset: int = 1000,
) -> Dict[str, Any]:
    unknown = [d for d in datasets if d not in DATASETS]
    if unknown:
        raise ValueError(f"Unknown infrastructure datasets: {', '.join(unknown)}")

    summary: Dict[str, Any] = {"tenant_id": tenant_id, "bbox": bbox, "created": 0, "updated": 0, "skipped": 0, "datasets": {}}
    for key in datasets:
        features = await _fetch_layer(key, bbox=bbox, limit=limit_per_dataset)
        ds = {"fetched": len(features), "created": 0, "updated": 0, "skipped": 0}
        for feature in features:
            payload = normalize_bc_infrastructure(key, feature, tenant_id=tenant_id)
            if not payload:
                ds["skipped"] += 1
                summary["skipped"] += 1
                continue
            created = _upsert(session, payload)
            label = "created" if created else "updated"
            ds[label] += 1
            summary[label] += 1
        summary["datasets"][key] = ds
    session.commit()
    return summary
