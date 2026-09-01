from app.services.scenario_simulation import _bounded, _scenario_priority


def test_scenario_priority_increases_with_risk_and_urgency():
    low = _scenario_priority({"risk_score": 0.2, "urgency_score": 0.2, "severity": "low"})
    high = _scenario_priority({"risk_score": 0.9, "urgency_score": 0.8, "severity": "critical"})
    assert high > low


def test_bounded_keeps_scores_in_range():
    assert _bounded(-1.0) == 0.0
    assert _bounded(0.5) == 0.5
    assert _bounded(2.0) == 1.0
