from app.services.decision_engine import policy_flags, rank_courses_of_action, risk_label


def test_rank_courses_of_action_prefers_lower_risk_and_policy_compliance():
    options = [
        {
            "name": "Observe",
            "confidence": 0.8,
            "risk_score": 0.2,
            "urgency_score": 0.4,
            "resource_score": 0.9,
            "reversibility_score": 1.0,
            "policy_score": 1.0,
        },
        {
            "name": "Escalate",
            "confidence": 0.8,
            "risk_score": 0.8,
            "urgency_score": 0.7,
            "resource_score": 0.6,
            "reversibility_score": 0.3,
            "policy_score": 0.6,
        },
    ]

    ranked = rank_courses_of_action(options)
    assert ranked[0].name == "Observe"
    assert ranked[0].score > ranked[1].score
    assert risk_label(ranked) == "low"


def test_policy_flags_surface_high_risk_and_low_policy_score():
    ranked = rank_courses_of_action([
        {
            "name": "Option A",
            "risk_score": 0.9,
            "policy_score": 0.4,
        }
    ])
    flags = policy_flags(ranked)
    assert any("policy score" in flag for flag in flags)
    assert any("very high" in flag for flag in flags)


def test_custom_weights_are_normalized():
    ranked = rank_courses_of_action(
        [{"name": "A"}, {"name": "B", "confidence": 0.9}],
        {"confidence": 10.0},
    )
    assert len(ranked) == 2
    assert ranked[0].score <= 1.0
