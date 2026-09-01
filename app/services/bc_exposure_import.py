from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import httpx
from sqlmodel import Session, select

from app.models.exposure import ExposureAsset

BC_IMAGERY_MAPSERVER = "https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_imagery_and_base_maps/MapServer"
BC_LEGAL_ADMIN_MAPSERVER = "https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_legal_admin_boundaries/MapServer"

SOURCE_SYSTEM = "BC-DataBC-ArcGIS"
DEFAULT_TIMEOUT_SECONDS = 15.0

DATASETS: Dict[str, Dict[str, Any]] = {
    "hospitals": {
        "url": f"{BC_IMAGERY_MAPSERVER}/0/query",
        "asset_type": "hospital",
        "name_fields": ["OCCUPANT_NAME", "ORGANIZATION_NAME"],
        "criticality": 0.95,
        "vulnerability": 0.65,
        "source_dataset": "Hospitals in BC / GSR_HOSPITALS_SVW",
    },
    "emergency_rooms": {
        "url": f"{BC_IMAGERY_MAPSERVER}/12/query",
        "asset_type": "emergency_room",
        "name_fields": ["ORGANIZATION_NAME", "OCCUPANT_NAME"],
        "criticality": 1.0,
        "vulnerability": 0.70,
        "source_dataset": "Emergency Rooms in BC / GSR_EMERGENCY_ROOMS_SV",
    },
    "municipalities": {
        "url": f"{BC_LEGAL_ADMIN_MAPSERVER}/9/query",
        "asset_type": "community",
        "name_fields": ["ADMIN_AREA_NAME"],
        "criticality": 0.80,
        "vulnerability": 0.60,
        "source_dataset": "Legally Defined Administrative Areas of BC Boundary Locations / ABMS_LGL_ADMIN_AREA_LOCS_SVW",
        "where": "ADMIN_AREA_TYPE='Municipality' OR ADMIN_AREA_TYPE='MUNICIPALITY'",
    },
}


class BCExposureImportError(RuntimeError):
    pass


async def _arcgis_features(dataset: Dict[str, Any], limit: int = 1000) -> List[Dict[str, Any]]:
    params = {
        "where": dataset.get("where") or "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": max(1, min(limit, 1000)),
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(dataset["url"], params=params, headers={"User-Agent": "SitRep/2.6 BCExposureImporter"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BCExposureImportError(str(exc)) from exc
    return list(payload.get("features") or [])


def _feature_point(feature: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") == "Point" and len(coordinates) >= 2:
        return float(coordinates[1]), float(coordinates[0])
    return None, None


def _first(properties: Dict[str, Any], names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = properties.get(name)
        if value not in (None, ""):
            return str(value)
    return None


def _source_id(dataset_key: str, feature: Dict[str, Any]) -> str:
    properties = feature.get("properties") or {}
    raw_id = feature.get("id") or properties.get("OBJECTID") or properties.get("objectid") or _first(properties, DATASETS[dataset_key]["name_fields"])
    return f"{dataset_key}:{raw_id}"


def normalize_bc_feature(dataset_key: str, feature: Dict[str, Any], tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    dataset = DATASETS[dataset_key]
    properties = feature.get("properties") or {}
    latitude, longitude = _feature_point(feature)
    if latitude is None or longitude is None:
        return None
    name = _first(properties, dataset["name_fields"]) or f"{dataset['asset_type']} {_source_id(dataset_key, feature)}"
    return {
        "tenant_id": tenant_id,
        "asset_type": dataset["asset_type"],
        "name": name,
        "latitude": latitude,
        "longitude": longitude,
        "population": None,
        "criticality_score": float(dataset["criticality"]),
        "vulnerability_score": float(dataset["vulnerability"]),
        "source_system": SOURCE_SYSTEM,
        "source_id": _source_id(dataset_key, feature),
        "properties": {
            "source_dataset": dataset["source_dataset"],
            "source_url": dataset["url"],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "bc_properties": properties,
        },
    }


def upsert_exposure_asset(session: Session, payload: Dict[str, Any]) -> tuple[ExposureAsset, bool]:
    existing = session.exec(
        select(ExposureAsset)
        .where(ExposureAsset.tenant_id == payload["tenant_id"])
        .where(ExposureAsset.source_system == payload["source_system"])
        .where(ExposureAsset.source_id == payload["source_id"])
    ).first()
    if existing:
        existing.name = payload["name"]
        existing.asset_type = payload["asset_type"]
        existing.latitude = payload["latitude"]
        existing.longitude = payload["longitude"]
        existing.criticality_score = payload["criticality_score"]
        existing.vulnerability_score = payload["vulnerability_score"]
        existing.properties = payload["properties"]
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        return existing, False
    asset = ExposureAsset(**payload)
    session.add(asset)
    return asset, True


async def import_bc_exposure_assets(
    session: Session,
    dataset_keys: List[str],
    tenant_id: str = "default",
    limit_per_dataset: int = 1000,
) -> Dict[str, Any]:
    unknown = [key for key in dataset_keys if key not in DATASETS]
    if unknown:
        raise ValueError(f"Unknown BC exposure datasets: {', '.join(unknown)}")

    summary: Dict[str, Any] = {"tenant_id": tenant_id, "datasets": {}, "created": 0, "updated": 0, "skipped": 0}
    for key in dataset_keys:
        features = await _arcgis_features(DATASETS[key], limit=limit_per_dataset)
        dataset_summary = {"fetched": len(features), "created": 0, "updated": 0, "skipped": 0}
        for feature in features:
            payload = normalize_bc_feature(key, feature, tenant_id=tenant_id)
            if not payload:
                dataset_summary["skipped"] += 1
                summary["skipped"] += 1
                continue
            _, created = upsert_exposure_asset(session, payload)
            label = "created" if created else "updated"
            dataset_summary[label] += 1
            summary[label] += 1
        summary["datasets"][key] = dataset_summary
    session.commit()
    return summary
