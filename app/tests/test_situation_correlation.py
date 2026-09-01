from datetime import datetime, timezone

from sqlmodel import SQLModel, Session, create_engine

from app.services.situation_correlation import correlate_observation, haversine_km


def _session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_haversine_nearby_points():
    distance = haversine_km(49.1659, -123.9401, 49.20, -123.90)
    assert 0 < distance < 10


def test_fire_and_weather_alert_join_same_emergency_situation():
    now = datetime.now(timezone.utc).isoformat()
    with _session() as session:
        fire = {
            "source_system": "NRCan-CWFIS",
            "source_type": "active_fire",
            "object_type": "wildfire active fire",
            "collected_at": now,
            "latitude": 49.20,
            "longitude": -123.90,
            "confidence": 0.75,
            "tenant_id": "pilot",
        }
        fire_result = correlate_observation(session, "obs-fire", fire)

        alert = {
            "source_system": "ECCC-GeoMet",
            "source_type": "weather_alert",
            "object_type": "weather hazard alert: strong wind warning",
            "collected_at": now,
            "latitude": 49.21,
            "longitude": -123.89,
            "confidence": 0.90,
            "tenant_id": "pilot",
        }
        alert_result = correlate_observation(session, "obs-alert", alert)

        assert fire_result["domain"] == "wildfire-emergency"
        assert alert_result["situation_id"] == fire_result["situation_id"]
        assert alert_result["created"] is False
        assert set(alert_result["source_types"]) == {"active_fire", "weather_alert"}
        assert alert_result["observation_count"] == 2
        assert alert_result["risk_score"] >= fire_result["risk_score"]
        assert alert_result["severity"] in {"high", "critical"}
