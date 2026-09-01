from app.services.mission_packs import build_candidate_options, select_mission_pack


def test_selects_maritime_arctic_pack_for_vessel_observation():
    observation = {
        "object_type": "unknown vessel",
        "source_type": "AIS",
        "source_system": "maritime-feed",
        "confidence": 0.88,
    }
    assert select_mission_pack(observation) == "canada-maritime-arctic"


def test_selects_wildfire_pack_for_smoke_observation():
    observation = {
        "object_type": "wildfire smoke plume",
        "source_type": "satellite",
        "source_system": "environment-feed",
        "confidence": 0.91,
    }
    assert select_mission_pack(observation) == "wildfire-emergency"


def test_build_candidate_options_preserves_human_authorization_constraints():
    observation = {"object_type": "unknown vessel", "confidence": 0.8}
    trigger = {"severity": "high", "reasons": ["tracking gate anomaly"]}

    options = build_candidate_options("canada-maritime-arctic", observation, trigger)

    assert len(options) >= 3
    assert all(option["confidence"] == 0.8 for option in options)
    assert all(any("human operator" in assumption.lower() for assumption in option["assumptions"]) for option in options)
    assert all(any("authorization" in constraint.lower() for constraint in option["constraints"]) for option in options)
