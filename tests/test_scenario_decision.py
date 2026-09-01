from app.services.scenario_decision import _bounded, _risk_level


def test_scenario_decision_risk_labels():
    assert _risk_level(0.85) == "critical"
    assert _risk_level(0.65) == "high"
    assert _risk_level(0.40) == "moderate"
    assert _risk_level(0.20) == "low"


def test_scenario_decision_scores_are_bounded():
    assert _bounded(-0.2) == 0.0
    assert _bounded(0.6) == 0.6
    assert _bounded(1.3) == 1.0
