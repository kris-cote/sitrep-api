from app.services.bc_exposure_import import normalize_bc_feature


def test_hospital_feature_normalizes_to_exposure_asset():
    feature = {
        "id": 123,
        "geometry": {"type": "Point", "coordinates": [-123.93, 49.17]},
        "properties": {"OCCUPANT_NAME": "Example General Hospital", "OBJECTID": 123},
    }
    asset = normalize_bc_feature("hospitals", feature, tenant_id="pilot")
    assert asset is not None
    assert asset["asset_type"] == "hospital"
    assert asset["name"] == "Example General Hospital"
    assert asset["latitude"] == 49.17
    assert asset["longitude"] == -123.93
    assert asset["criticality_score"] >= 0.9
    assert asset["source_id"] == "hospitals:123"
    assert asset["tenant_id"] == "pilot"


def test_municipality_feature_normalizes_to_community():
    feature = {
        "id": 44,
        "geometry": {"type": "Point", "coordinates": [-123.94, 49.16]},
        "properties": {"ADMIN_AREA_NAME": "Nanaimo", "OBJECTID": 44},
    }
    asset = normalize_bc_feature("municipalities", feature)
    assert asset is not None
    assert asset["asset_type"] == "community"
    assert asset["name"] == "Nanaimo"
    assert asset["source_system"] == "BC-DataBC-ArcGIS"
