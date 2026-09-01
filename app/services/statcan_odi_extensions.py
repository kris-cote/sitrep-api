from app.services.statcan_odi_import import ODI_TYPES

# Additional ODI v2 layers. These use the same dynamic ArcGIS layer discovery,
# provenance and planning-context policy as the core ODI importer.
ODI_TYPES.update({
    "oil_and_gas": {
        "match": ["oil and gas", "oil & gas"],
        "target": "infrastructure",
        "category": "fuel",
        "subtype": "oil_and_gas",
        "criticality": 0.88,
        "vulnerability": 0.52,
    },
    "railways": {
        "match": ["railway"],
        "target": "infrastructure",
        "category": "transport",
        "subtype": "railway",
        "criticality": 0.82,
        "vulnerability": 0.48,
    },
    "ports_and_marinas": {
        "match": ["ports and marinas", "port", "marina"],
        "target": "exposure",
        "asset_type": "port",
        "criticality": 0.84,
        "vulnerability": 0.43,
    },
    "bridges_and_tunnels": {
        "match": ["bridges and tunnels", "bridge", "tunnel"],
        "target": "infrastructure",
        "category": "transport",
        "subtype": "bridge_tunnel",
        "criticality": 0.86,
        "vulnerability": 0.55,
    },
    "low_carbon": {
        "match": ["low carbon"],
        "target": "infrastructure",
        "category": "energy",
        "subtype": "low_carbon",
        "criticality": 0.72,
        "vulnerability": 0.45,
    },
    "solid_waste": {
        "match": ["solid waste"],
        "target": "exposure",
        "asset_type": "waste_facility",
        "criticality": 0.65,
        "vulnerability": 0.45,
    },
    "wastewater_stormwater": {
        "match": ["wastewater and stormwater", "wastewater", "stormwater", "storm water"],
        "target": "infrastructure",
        "category": "water",
        "subtype": "wastewater_stormwater",
        "criticality": 0.82,
        "vulnerability": 0.52,
    },
})
