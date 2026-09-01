from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
from sqlmodel import Session, select

from app.models.exposure import ExposureAsset
from app.services.canada_infrastructure_import import JURISDICTIONS

ODHF_ARCGIS_QUERY = "https://maps-cartes.services.geo.ca/server2_serveur2/rest/services/StatCan/OpenDatabaseHealthFacilities/MapServer/0/query"
ISED_PLACENAMES_CSV = "https://ised-isde.canada.ca/app/scr/sittibc/web/api/openData/MAG_EXO.CSV"
DEFAULT_TIMEOUT_SECONDS = 20.0

PROVINCE_ALIASES = {
    "AB": {"AB", "ALBERTA", "48"},
    "BC": {"BC", "B.C.", "BRITISH COLUMBIA", "COLOMBIE-BRITANNIQUE", "59"},
    "MB": {"MB", "MANITOBA", "46"},
    "NB": {"NB", "NEW BRUNSWICK", "NOUVEAU-BRUNSWICK", "13"},
    "NL": {"NL", "NEWFOUNDLAND AND LABRADOR", "TERRE-NEUVE-ET-LABRADOR", "10"},
    "NS": {"NS", "NOVA SCOTIA", "NOUVELLE-ÉCOSSE", "12"},
    "NT": {"NT", "NWT", "NORTHWEST TERRITORIES", "TERRITOIRES DU NORD-OUEST", "61"},
    "NU": {"NU", "NUNAVUT", "62"},
    "ON": {"ON", "ONTARIO", "35"},
    "PE": {"PE", "PEI", "PRINCE EDWARD ISLAND", "ÎLE-DU-PRINCE-ÉDOUARD", "11"},
    "QC": {"QC", "QUEBEC", "QUÉBEC", "24"},
    "SK": {"SK", "SASKATCHEWAN", "47"},
    "YT": {"YT", "YUKON", "60"},
}


class ExposureFeedError(RuntimeError):
    pass


def validate_jurisdiction(jurisdiction: str) -> str:
    code = jurisdiction.upper()
    if code not in JURISDICTIONS:
        raise ValueError(f"Unsupported jurisdiction: {jurisdiction}")
    return code


def _matches_jurisdiction(value: Any, jurisdiction: str) -> bool:
    if value in (None, ""):
        return True
    code = validate_jurisdiction(jurisdiction)
    return str(value).strip().upper() in {v.upper() for v in PROVINCE_ALIASES[code]}


async def _get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers={"User-Agent": "SitRep/3.0 ExposureConnector"})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ExposureFeedError(str(exc)) from exc


async def _get_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "SitRep/3.0 ExposureConnector"})
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as exc:
        raise ExposureFeedError(str(exc)) from exc


def _pick(mapping: Dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for name in names:
        if name.lower() in lowered and lowered[name.lower()] not in (None, ""):
            return lowered[name.lower()]
    return default


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _facility_type(attributes: Dict[str, Any]) -> str:
    text = str(_pick(attributes, ("facility_type", "facilitytype", "type", "odhf_facility_type", "category"), "health facility"))
    lowered = text.lower()
    if "hospital" in lowered:
        return "hospital"
    if any(term in lowered for term in ("nursing", "residential", "long-term", "long term")):
        return "care_facility"
    return "health_facility"


def _criticality_for_type(asset_type: str) -> float:
    return {"hospital": 0.95, "care_facility": 0.85, "health_facility": 0.75, "community": 0.80, "first_nations_community": 0.90}.get(asset_type, 0.60)


def _upsert_asset(session: Session, payload: Dict[str, Any]) -> Tuple[ExposureAsset, bool]:
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
        existing.population = payload.get("population")
        existing.criticality_score = payload["criticality_score"]
        existing.vulnerability_score = payload["vulnerability_score"]
        existing.properties = payload.get("properties", {})
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        return existing, False
    asset = ExposureAsset(**payload)
    session.add(asset)
    return asset, True


async def fetch_odhf_facilities(limit: int = 5000) -> List[Dict[str, Any]]:
    payload = await _get_json(ODHF_ARCGIS_QUERY, {"f": "json", "where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326", "resultRecordCount": max(1, min(limit, 5000))})
    if payload.get("error"):
        raise ExposureFeedError(str(payload["error"]))
    return payload.get("features", [])


def odhf_feature_to_asset(feature: Dict[str, Any], jurisdiction: str = "BC", tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    code = validate_jurisdiction(jurisdiction)
    attributes = feature.get("attributes") or {}
    geometry = feature.get("geometry") or {}
    province = _pick(attributes, ("province", "prov", "prname", "province_territory", "province_territoire"), "")
    if not _matches_jurisdiction(province, code):
        return None
    latitude = _float(geometry.get("y")) or _float(_pick(attributes, ("latitude", "lat")))
    longitude = _float(geometry.get("x")) or _float(_pick(attributes, ("longitude", "lon", "lng")))
    if latitude is None or longitude is None:
        return None
    source_id = str(_pick(attributes, ("index", "odhf_id", "facility_id", "objectid", "fid"), "")) or f"{latitude:.6f},{longitude:.6f}"
    name = str(_pick(attributes, ("facility_name", "name", "facility", "odhf_facility_name"), "Health facility"))
    asset_type = _facility_type(attributes)
    return {"tenant_id": tenant_id, "asset_type": asset_type, "name": name, "latitude": latitude, "longitude": longitude, "population": None, "criticality_score": _criticality_for_type(asset_type), "vulnerability_score": 0.65 if asset_type in {"hospital", "care_facility"} else 0.55, "source_system": "StatCan-ODHF", "source_id": source_id, "properties": {**attributes, "jurisdiction": code}}


async def import_odhf_jurisdiction(session: Session, jurisdiction: str, tenant_id: str = "default", limit: int = 5000) -> Dict[str, Any]:
    code = validate_jurisdiction(jurisdiction)
    features = await fetch_odhf_facilities(limit=limit)
    inserted = updated = skipped = 0
    for feature in features:
        payload = odhf_feature_to_asset(feature, jurisdiction=code, tenant_id=tenant_id)
        if not payload:
            skipped += 1
            continue
        _, created = _upsert_asset(session, payload)
        inserted += int(created); updated += int(not created)
    session.commit()
    return {"source": "StatCan-ODHF", "jurisdiction": code, "inserted": inserted, "updated": updated, "skipped": skipped, "fetched": len(features)}


def placename_row_to_asset(row: Dict[str, Any], jurisdiction: str = "BC", tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    code = validate_jurisdiction(jurisdiction)
    province = _pick(row, ("province", "prov", "pr", "province_territory", "province_territoire"), "")
    if not _matches_jurisdiction(province, code):
        return None
    latitude = _float(_pick(row, ("latitude", "lat", "latitude_dd")))
    longitude = _float(_pick(row, ("longitude", "lon", "lng", "longitude_dd")))
    if latitude is None or longitude is None:
        return None
    name = str(_pick(row, ("name", "placename", "place_name", "community", "nom"), "Community"))
    source_id = str(_pick(row, ("id", "geonameid", "cgndb_id", "community_id", "uid"), f"{latitude:.6f},{longitude:.6f}:{name}"))
    place_type = str(_pick(row, ("type", "place_type", "category", "designation"), "community"))
    first_nations = any(term in place_type.lower() for term in ("first nation", "indigenous", "reserve", "inuit", "métis", "metis"))
    asset_type = "first_nations_community" if first_nations else "community"
    population_value = _pick(row, ("population", "pop", "population_2021", "pop2021"))
    try:
        population = int(float(population_value)) if population_value not in (None, "") else None
    except (TypeError, ValueError):
        population = None
    return {"tenant_id": tenant_id, "asset_type": asset_type, "name": name, "latitude": latitude, "longitude": longitude, "population": population, "criticality_score": _criticality_for_type(asset_type), "vulnerability_score": 0.65 if first_nations else 0.55, "source_system": "ISED-GeolocatedPlacenames", "source_id": source_id, "properties": {**row, "jurisdiction": code}}


async def import_ised_placenames(session: Session, jurisdiction: str, tenant_id: str = "default", limit: int = 50000) -> Dict[str, Any]:
    code = validate_jurisdiction(jurisdiction)
    text = await _get_text(ISED_PLACENAMES_CSV)
    reader = csv.DictReader(io.StringIO(text))
    inserted = updated = skipped = fetched = 0
    for row in reader:
        if fetched >= limit:
            break
        fetched += 1
        payload = placename_row_to_asset(row, jurisdiction=code, tenant_id=tenant_id)
        if not payload:
            skipped += 1
            continue
        _, created = _upsert_asset(session, payload)
        inserted += int(created); updated += int(not created)
    session.commit()
    return {"source": "ISED-GeolocatedPlacenames", "jurisdiction": code, "inserted": inserted, "updated": updated, "skipped": skipped, "fetched": fetched}


# Backward-compatible BC wrappers.
async def import_odhf_bc(session: Session, tenant_id: str = "default", limit: int = 5000) -> Dict[str, Any]:
    return await import_odhf_jurisdiction(session, "BC", tenant_id, limit)

async def import_ised_bc_placenames(session: Session, tenant_id: str = "default", limit: int = 50000) -> Dict[str, Any]:
    return await import_ised_placenames(session, "BC", tenant_id, limit)
