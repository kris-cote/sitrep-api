from app.services.canadian_feeds import eccc_alert_feature_to_observation
from app.services.feed_ingestion import source_fingerprint


def test_source_fingerprint_is_stable_and_change_sensitive():
    a = {"id": "fire-1", "properties": {"status": "active", "size": 20}}
    b = {"properties": {"size": 20, "status": "active"}, "id": "fire-1"}
    c = {"id": "fire-1", "properties": {"status": "active", "size": 21}}

    assert source_fingerprint(a) == source_fingerprint(b)
    assert source_fingerprint(a) != source_fingerprint(c)


def test_eccc_weather_alert_normalizes_to_public_sitrep_observation():
    feature = {
        "id": "weather-alerts.123",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-124.0, 49.0], [-123.0, 49.0], [-123.0, 50.0], [-124.0, 50.0], [-124.0, 49.0]]],
        },
        "properties": {
            "alert_type": "warning",
            "risk_colour_en": "red",
            "province": "BC",
            "sent": "2026-09-01T12:00:00Z",
        },
    }

    observation = eccc_alert_feature_to_observation(feature, tenant_id="pilot")

    assert observation["source_system"] == "ECCC-GeoMet"
    assert observation["source_type"] == "weather_alert"
    assert "weather hazard alert" in observation["object_type"]
    assert observation["classification_tag"] == "PUBLIC"
    assert observation["tenant_id"] == "pilot"
    assert observation["features"]["feature_id"] == "weather-alerts.123"
    assert observation["features"]["severity"] == "red"
    assert observation["latitude"] is not None
    assert observation["longitude"] is not None
