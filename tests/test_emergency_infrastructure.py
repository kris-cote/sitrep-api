from app.services.canada_emergency_import import normalize_on_affes, normalize_qc_fire


def test_ontario_affes_classifies_fire_and_air_facilities():
    fire = normalize_on_affes({"geometry": {"type": "Point", "coordinates": [-84.0, 49.0]}, "properties": {"FACILITY_NAME": "North Fire Base", "FACILITY_TYPE": "Fire Base"}})
    heli = normalize_on_affes({"geometry": {"type": "Point", "coordinates": [-83.0, 48.0]}, "properties": {"FACILITY_NAME": "Helibase", "FACILITY_TYPE": "Helipad"}})
    assert fire["asset_type"] == "fire_station"
    assert heli["asset_type"] == "heliport"
    assert fire["criticality_score"] > 0.9


def test_quebec_fire_station_normalization():
    item = normalize_qc_fire({"id": "station.1", "geometry": {"type": "Point", "coordinates": [-71.2, 46.8]}, "properties": {"NOM": "Caserne 1"}})
    assert item["asset_type"] == "fire_station"
    assert item["name"] == "Caserne 1"
    assert item["properties"]["jurisdiction"] == "QC"
