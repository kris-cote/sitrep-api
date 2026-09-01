from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/connectors/canada/odi", tags=["canada-open-database-infrastructure"])

ODI_CATALOG = {
    "source": "Statistics Canada Open Database of Infrastructure (ODI) v2",
    "release_date": "2024-11-13",
    "licence": "Open Government Licence - Canada",
    "catalogue": "34-26-0003",
    "role": "national planning-context fallback when a fresher jurisdiction-specific source is unavailable",
    "categories": {
        "electrical_grid": {"target": "infrastructure", "category": "electric"},
        "airports": {"target": "exposure", "asset_type": "airport"},
        "telecommunications": {"target": "infrastructure", "category": "telecom"},
        "potable_water": {"target": "infrastructure", "category": "water"},
        "oil_and_gas": {"target": "infrastructure", "category": "fuel"},
        "railways": {"target": "infrastructure", "category": "transport"},
        "ports_and_marinas": {"target": "exposure", "asset_type": "port"},
        "bridges_and_tunnels": {"target": "infrastructure", "category": "transport"},
        "low_carbon": {"target": "infrastructure", "category": "energy"},
        "solid_waste": {"target": "exposure", "asset_type": "waste_facility"},
        "wastewater_stormwater": {"target": "infrastructure", "category": "water"},
    },
    "policy": {
        "planning_context_only": True,
        "prefer_fresher_authoritative_jurisdiction_feed": True,
        "do_not_infer_dependency_edges_from_proximity": True,
    },
}


@router.get("/catalog")
def odi_catalog():
    return ODI_CATALOG
