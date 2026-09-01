from app.services.scenario_comparison import _continuity, _reversibility, _resource_change_burden


def test_more_disruptive_infrastructure_branch_has_lower_continuity():
    mild = {"infrastructure_changes": [{"feature_id": "hwy", "state": "degraded"}]}
    severe = {"infrastructure_changes": [{"feature_id": "hwy", "state": "closed"}, {"feature_id": "grid", "state": "failed"}]}
    assert _continuity(mild) > _continuity(severe)


def test_explicit_reversibility_overrides_heuristic():
    branch = {"reversibility_score": 0.95, "infrastructure_changes": [{"feature_id": "x", "state": "failed"}]}
    assert _reversibility(branch) == 0.95


def test_unavailable_resource_change_costs_more_than_available():
    unavailable = {"resource_changes": [{"capability_id": "a", "availability_status": "unavailable"}]}
    available = {"resource_changes": [{"capability_id": "a", "availability_status": "available"}]}
    assert _resource_change_burden(unavailable) > _resource_change_burden(available)
