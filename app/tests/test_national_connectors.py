import io
import zipfile

from app.services.canada_rail_import import _kml_lines
from app.services.canadian_exposure_feeds import odhf_feature_to_asset, placename_row_to_asset


def test_odhf_filters_by_jurisdiction():
    feature = {
        "attributes": {"province": "Ontario", "facility_name": "Example Hospital", "facility_type": "Hospital", "objectid": 1},
        "geometry": {"x": -79.38, "y": 43.65},
    }
    assert odhf_feature_to_asset(feature, jurisdiction="ON") is not None
    assert odhf_feature_to_asset(feature, jurisdiction="AB") is None


def test_placename_filters_by_jurisdiction():
    row = {"province": "48", "name": "Example Alberta Place", "latitude": "53.5", "longitude": "-113.5", "id": "x1"}
    asset = placename_row_to_asset(row, jurisdiction="AB")
    assert asset is not None
    assert asset["properties"]["jurisdiction"] == "AB"
    assert placename_row_to_asset(row, jurisdiction="BC") is None


def test_nrwn_kml_parser_extracts_track_lines():
    kml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Test Track</name>
    <LineString><coordinates>-123.0,49.0,0 -123.1,49.1,0</coordinates></LineString>
    </Placemark></Document></kml>'''
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("track.kml", kml)
    features = _kml_lines(buffer.getvalue(), 10)
    assert len(features) == 1
    assert features[0]["name"] == "Test Track"
    assert features[0]["geometry"]["type"] == "LineString"
    assert len(features[0]["geometry"]["coordinates"]) == 2
