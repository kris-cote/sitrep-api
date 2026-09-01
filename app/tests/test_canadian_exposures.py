from app.services.canadian_exposure_feeds import odhf_feature_to_asset, placename_row_to_asset


def test_odhf_bc_hospital_normalizes_to_exposure_asset():
    feature = {
        "attributes": {
            "OBJECTID": 101,
            "facility_name": "Example General Hospital",
            "facility_type": "Hospital",
            "province": "BC",
        },
        "geometry": {"x": -123.9, "y": 49.2},
    }

    asset = odhf_feature_to_asset(feature, tenant_id="pilot")

    assert asset is not None
    assert asset["asset_type"] == "hospital"
    assert asset["source_system"] == "StatCan-ODHF"
    assert asset["tenant_id"] == "pilot"
    assert asset["latitude"] == 49.2
    assert asset["longitude"] == -123.9
    assert asset["criticality_score"] >= 0.9


def test_non_bc_odhf_facility_is_skipped():
    feature = {
        "attributes": {"OBJECTID": 5, "facility_name": "Elsewhere", "province": "AB"},
        "geometry": {"x": -114.0, "y": 51.0},
    }
    assert odhf_feature_to_asset(feature) is None


def test_first_nations_placename_receives_higher_priority_type():
    row = {
        "id": "abc123",
        "name": "Example First Nation",
        "province": "BC",
        "latitude": "49.10",
        "longitude": "-124.00",
        "type": "First Nation Community",
    }

    asset = placename_row_to_asset(row)

    assert asset is not None
    assert asset["asset_type"] == "first_nations_community"
    assert asset["criticality_score"] >= 0.85
