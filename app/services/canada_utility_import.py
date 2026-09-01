from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlmodel import Session, select

from app.models.infrastructure import InfrastructureFeature

DEFAULT_TIMEOUT_SECONDS = 30.0
NB_UTILITIES_GEOJSON = "https://gnb.socrata.com/api/geospatial/y3vu-vr3p?method=export&format=GeoJSON"

UTILITY_COVERAGE: Dict[str, Dict[str, Any]] = {
    "BC": {"status": "supported", "source": "Government of British Columbia public transmission lines", "adapter": "bc-transmission"},
    "NB": {"status": "supported", "source": "Government of New Brunswick Utilities", "adapter": "nb-utilities"},
    "ON": {"status": "available_source", "source": "Ontario Utility Line", "adapter": "adapter_pending", "note": "Dataset includes power, water, communications and fuel lines; source is older and should carry freshness metadata."},
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


def normalize_nb_utility(feature: Dict[str, Any], tenant_id: str = "default") -> Optional[Dict[str, Any]]:
    geometry = feature.get("geometry") or {}
    if not geometry:
        return None
    props = dict(feature.get("properties") or {})
    text = " ".join(str(v) for v in props.values() if v is not None).lower()
    if "power" in text or "electric" in text or "transmission" in text:
        category, subtype, criticality = "electric", "transmission_line", 0.88
    elif "pipeline" in text or "gas" in text or "fuel" in text:
        category, subtype, criticality = "fuel", "pipeline", 0.82
    else:
        category, subtype, criticality = "utility", "utility_line", 0.65
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


async def import_nb_utilities(session: Session, tenant_id: str = "default", limit: int = 5000) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(NB_UTILITIES_GEOJSON, headers={"User-Agent": "SitRep/3.1 UtilityImporter"})
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
