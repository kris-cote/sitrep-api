from app.services.operational_forecast import _forecast_priority, _trend_signal


class DummySituation:
    risk_score = 0.6
    urgency_score = 0.6
    severity = "high"
    context = {}
    correlation_reasons = []


def test_no_trend_evidence_keeps_forecast_priority_stable():
    situation = DummySituation()
    short = _forecast_priority(situation, 0.5)
    long = _forecast_priority(situation, 24.0)
    assert short["forecast_priority"] == short["current_priority"]
    assert long["forecast_priority"] == long["current_priority"]
    assert long["uncertainty"] > short["uncertainty"]


def test_worsening_explicit_trend_increases_future_priority():
    situation = DummySituation()
    situation.context = {"forecast_trend": 0.8}
    short = _forecast_priority(situation, 0.5)
    long = _forecast_priority(situation, 24.0)
    assert long["forecast_priority"] > short["forecast_priority"]
    assert _trend_signal(situation) == 0.8
