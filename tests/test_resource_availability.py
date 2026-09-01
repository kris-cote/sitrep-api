from app.services.resource_availability import apply_resource_profile_to_options, required_resource_group


def test_required_resource_group_detects_air_support():
    option = {"name": "Deploy aviation support", "description": "Task a helicopter for reconnaissance"}
    assert required_resource_group(option) == "air"


def test_resource_profile_adjusts_air_coa_without_zeroing_sparse_data():
    options = [{"name": "Deploy aviation support", "description": "Use helicopter", "resource_score": 0.7, "rationale": []}]
    profile = {
        "resource_confidence": 0.8,
        "groups": {
            "air": {"score": 0.9, "count": 2, "coverage_confidence": 0.8, "top_resources": [{"name": "Airbase A"}]},
            "general": {"score": 0.5, "count": 1, "coverage_confidence": 0.5, "top_resources": []},
        },
    }
    result = apply_resource_profile_to_options(options, profile)
    assert result[0]["resource_score"] > 0.7
    assert result[0]["metadata"]["resource_availability"]["required_group"] == "air"


def test_missing_public_resource_does_not_zero_coa():
    options = [{"name": "Evacuate community", "description": "Move residents to reception centres", "resource_score": 0.6, "rationale": []}]
    profile = {
        "resource_confidence": 0.2,
        "groups": {
            "shelter": {"score": 0.25, "count": 0, "coverage_confidence": 0.25, "top_resources": []},
            "general": {"score": 0.25, "count": 0, "coverage_confidence": 0.25, "top_resources": []},
        },
    }
    result = apply_resource_profile_to_options(options, profile)
    assert result[0]["resource_score"] > 0.45
