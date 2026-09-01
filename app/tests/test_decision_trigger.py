from app.services.decision_trigger import evaluate_decision_trigger


def test_high_risk_observation_triggers_decision_analysis():
    result = evaluate_decision_trigger(
        observation={
            "confidence": 0.92,
            "object_type": "unknown vessel anomaly",
            "classification_tag": "UNCLASSIFIED",
        },
        tracking={"association_score": 0.31, "gate_result": "failed"},
        fusion={"requires_attention": True},
    )

    assert result["should_trigger"] is True
    assert result["severity"] == "high"
    assert result["human_authorization_required"] is True


def test_routine_observation_continues_monitoring():
    result = evaluate_decision_trigger(
        observation={
            "confidence": 0.65,
            "object_type": "known vehicle",
            "classification_tag": "UNCLASSIFIED",
        },
        tracking={"association_score": 0.91, "gate_result": True},
        fusion={},
    )

    assert result["should_trigger"] is False
    assert result["next_step"] == "continue_monitoring"
