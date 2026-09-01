from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.models.db import get_session
from app.services.statcan_odi_import import ODIImportError, import_odi, odi_catalog as service_catalog

router = APIRouter(prefix="/api/v1/connectors/canada/odi", tags=["canada-open-database-infrastructure"])

ODI_CATALOG = {
    "source": "Statistics Canada Open Database of Infrastructure (ODI) v2",
    "release_date": "2024-11-13",
    "licence": "Open Government Licence - Canada",
    "catalogue": "34-26-0003",
    "role": "national planning-context fallback when a fresher jurisdiction-specific source is unavailable",
    "categories": {
        "electric_grid": {"target": "infrastructure", "category": "electric", "importable": True},
        "airports": {"target": "exposure", "asset_type": "airport", "importable": True},
        "telecommunications": {"target": "infrastructure", "category": "telecom", "importable": True},
        "potable_water": {"target": "infrastructure", "category": "water", "importable": True},
        "oil_and_gas": {"target": "infrastructure", "category": "fuel", "importable": False},
        "railways": {"target": "infrastructure", "category": "transport", "importable": False},
        "ports_and_marinas": {"target": "exposure", "asset_type": "port", "importable": False},
        "bridges_and_tunnels": {"target": "infrastructure", "category": "transport", "importable": False},
        "low_carbon": {"target": "infrastructure", "category": "energy", "importable": False},
        "solid_waste": {"target": "exposure", "asset_type": "waste_facility", "importable": False},
        "wastewater_stormwater": {"target": "infrastructure", "category": "water", "importable": False},
    },
    "policy": {
        "planning_context_only": True,
        "prefer_fresher_authoritative_jurisdiction_feed": True,
        "do_not_infer_dependency_edges_from_proximity": True,
    },
}


@router.get("/catalog")
def odi_catalog():
    payload = dict(ODI_CATALOG)
    payload["live_adapter"] = service_catalog()
    return payload


@router.post("/import")
async def import_odi_category(
    odi_type: str = Query(..., description="airports, electric_grid, telecommunications, potable_water"),
    jurisdiction: str | None = Query(default=None, min_length=2, max_length=2, description="Optional province/territory code"),
    bbox: str | None = Query(default=None, description="Optional minLon,minLat,maxLon,maxLat"),
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    limit: int = Query(default=5000, ge=1, le=5000),
    session: Session = Depends(get_session),
):
    try:
        return await import_odi(
            session=session,
            odi_type=odi_type,
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            bbox=bbox,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ODIImportError as exc:
        raise HTTPException(status_code=502, detail={"upstream": "Statistics Canada ODI / Esri Canada", "error": str(exc)}) from exc
