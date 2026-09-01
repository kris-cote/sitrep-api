from app.services.canada_utility_import import normalize_on_utility, utility_coverage


def test_ontario_power_line_classification_and_freshness():
    feature = {
        "id": 42,
        "geometry": {"type": "LineString", "coordinates": [[-79.0, 44.0], [-78.9, 44.1]]},
        "properties": {"UTILITY_LINE_TYPE": "Hydro Line"},
    }
    item = normalize_on_utility(feature)
    assert item is not None
    assert item["category"] == "electric"
    assert item["subtype"] == "transmission_line"
    assert item["properties"]["planning_context_only"] is True
    assert item["properties"]["source_data_range_end"] == "2008-06-12"


def test_ontario_water_and_telecom_classification():
    water = normalize_on_utility({
        "id": 1,
        "geometry": {"type": "LineString", "coordinates": [[-80, 43], [-80.1, 43.1]]},
        "properties": {"TYPE": "Water pipeline"},
    })
    telecom = normalize_on_utility({
        "id": 2,
        "geometry": {"type": "LineString", "coordinates": [[-80, 43], [-80.1, 43.1]]},
        "properties": {"TYPE": "Communication line"},
    })
    assert water["category"] == "water"
    assert telecom["category"] == "telecom"
    assert utility_coverage()["ON"]["status"] == "supported_planning_context"
