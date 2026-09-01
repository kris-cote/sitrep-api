from app.services.canada_utility_import import normalize_nb_utility, utility_coverage


def test_nb_power_line_classification():
    feature = {
        "id": "1",
        "geometry": {"type": "LineString", "coordinates": [[-66.7, 45.9], [-66.6, 46.0]]},
        "properties": {"TYPE": "Power transmission line"},
    }
    item = normalize_nb_utility(feature)
    assert item is not None
    assert item["category"] == "electric"
    assert item["subtype"] == "transmission_line"
    assert item["properties"]["jurisdiction"] == "NB"


def test_nb_pipeline_classification():
    feature = {
        "id": "2",
        "geometry": {"type": "LineString", "coordinates": [[-65.8, 45.2], [-65.7, 45.3]]},
        "properties": {"TYPE": "Natural gas pipeline"},
    }
    item = normalize_nb_utility(feature)
    assert item is not None
    assert item["category"] == "fuel"
    assert item["subtype"] == "pipeline"


def test_utility_coverage_is_explicit_for_all_jurisdictions():
    coverage = utility_coverage()
    expected = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
    assert set(coverage) == expected
    assert coverage["BC"]["status"] == "supported"
    assert coverage["NB"]["status"] == "supported"
