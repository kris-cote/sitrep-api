from app.routes.situations import SituationCreate, SituationUpdate, DemoWildfireRequest


def test_situation_create_defaults():
    payload = SituationCreate(title="Test Situation")
    assert payload.tenant_id == "default"
    assert payload.radius_km == 25.0
    assert payload.risk_score == 0.0


def test_situation_update_allows_partial_changes():
    payload = SituationUpdate(risk_score=0.8, severity="high")
    data = payload.model_dump(exclude_unset=True)
    assert data["risk_score"] == 0.8
    assert data["severity"] == "high"
    assert "title" not in data


def test_demo_wildfire_defaults_to_vancouver_island_training_scenario():
    payload = DemoWildfireRequest()
    assert 48.0 < payload.latitude < 51.0
    assert -126.0 < payload.longitude < -123.0
    assert payload.radius_km > 0
