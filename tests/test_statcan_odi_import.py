from app.services.statcan_odi_import import normalize_odi_feature


def test_airport_normalizes_to_exposure():
    feature = {
        "id": 1,
        "geometry": {"type": "Point", "coordinates": [-123.94, 49.05]},
        "properties": {"NAME": "Example Airport", "PRUID": "59"},
    }
    item = normalize_odi_feature(feature, "airports", "https://example/6", tenant_id="t1")
    assert item is not None
    assert item["target"] == "exposure"
    assert item["payload"]["asset_type"] == "airport"
    assert item["payload"]["properties"]["planning_context_only"] is True


def test_electric_grid_normalizes_to_infrastructure():
    feature = {
        "id": "abc",
        "geometry": {"type": "LineString", "coordinates": [[-114.1, 51.0], [-114.0, 51.1]]},
        "properties": {"NAME": "Grid feature", "PROV": "Alberta"},
    }
    item = normalize_odi_feature(feature, "electric_grid", "https://example/8")
    assert item is not None
    assert item["target"] == "infrastructure"
    assert item["payload"]["category"] == "electric"
    assert item["payload"]["subtype"] == "electric_grid"


def test_telecom_and_water_classification():
    telecom = normalize_odi_feature(
        {"id": 2, "geometry": {"type": "Point", "coordinates": [-79.3, 43.7]}, "properties": {}},
        "telecommunications",
        "https://example/9",
    )
    water = normalize_odi_feature(
        {"id": 3, "geometry": {"type": "Point", "coordinates": [-97.1, 49.9]}, "properties": {}},
        "potable_water",
        "https://example/10",
    )
    assert telecom["payload"]["category"] == "telecom"
    assert water["payload"]["category"] == "water"
