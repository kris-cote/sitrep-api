from app.services.canadian_feeds import cwfis_feature_to_observation, normalize_cwfis_features


def test_cwfis_point_feature_normalizes_to_sitrep_observation():
    feature = {
        "id": "activefires_current.123",
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-123.9, 49.2]},
        "properties": {"agency": "BC", "status": "active"},
    }

    observation = cwfis_feature_to_observation(feature, tenant_id="pilot")

    assert observation["source_system"] == "NRCan-CWFIS"
    assert observation["source_type"] == "active_fire"
    assert observation["object_type"] == "wildfire active fire"
    assert observation["classification_tag"] == "PUBLIC"
    assert observation["tenant_id"] == "pilot"
    assert observation["longitude"] == -123.9
    assert observation["latitude"] == 49.2
    assert observation["features"]["feature_id"] == "activefires_current.123"


def test_normalize_cwfis_features_preserves_count():
    features = [
        {"id": "1", "geometry": {"type": "Point", "coordinates": [-123.0, 49.0]}, "properties": {}},
        {"id": "2", "geometry": {"type": "Point", "coordinates": [-124.0, 50.0]}, "properties": {}},
    ]

    observations = normalize_cwfis_features(features)

    assert len(observations) == 2
    assert all(item["source_system"] == "NRCan-CWFIS" for item in observations)
