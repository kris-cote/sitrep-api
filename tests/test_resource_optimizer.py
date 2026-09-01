from app.services.resource_optimizer import _situation_priority


class DummySituation:
    def __init__(self, risk, urgency, severity):
        self.risk_score = risk
        self.urgency_score = urgency
        self.severity = severity


def test_critical_high_urgency_situation_ranks_above_low_risk():
    critical = DummySituation(0.9, 0.9, "critical")
    low = DummySituation(0.2, 0.2, "low")
    assert _situation_priority(critical) > _situation_priority(low)


def test_priority_is_bounded():
    extreme = DummySituation(5.0, 5.0, "critical")
    assert 0.0 <= _situation_priority(extreme) <= 1.0
