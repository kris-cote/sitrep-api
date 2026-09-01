from app.services.resource_availability import STATUS_FACTOR


def test_availability_status_factors_are_conservative():
    assert STATUS_FACTOR["available"] > STATUS_FACTOR["limited"]
    assert STATUS_FACTOR["limited"] > STATUS_FACTOR["maintenance"]
    assert STATUS_FACTOR["unavailable"] == 0.0


def test_unknown_is_not_treated_as_available():
    assert STATUS_FACTOR["unknown"] < STATUS_FACTOR["available"]
    assert STATUS_FACTOR["unknown"] > STATUS_FACTOR["unavailable"]
