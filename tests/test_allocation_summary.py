from app.services.allocation_summary import build_allocation_summary


def test_allocation_summary_surfaces_priorities_conflicts_and_policy():
    plan = {
        "tenant_id": "default",
        "active_situation_count": 2,
        "capability_count": 1,
        "active_allocation_count": 0,
        "response_packages": [
            {
                "situation_id": "critical-fire",
                "situation_title": "Critical Fire",
                "priority_score": 0.9,
                "package_score": 0.88,
                "package_confidence": 0.82,
                "missing_resource_groups": ["medical"],
                "recommended_resources": [{"severity": "critical"}],
            },
            {
                "situation_id": "high-fire",
                "situation_title": "High Fire",
                "priority_score": 0.7,
                "package_score": 0.75,
                "package_confidence": 0.74,
                "missing_resource_groups": [],
                "recommended_resources": [{"severity": "high"}],
            },
        ],
        "proposals": [
            {"situation_id": "critical-fire", "situation_title": "Critical Fire", "priority_score": 0.9, "capability_id": "crew-1", "resource_name": "Crew Alpha", "resource_type": "wildland_fire_crew", "resource_group": "fire", "proposed_fraction": 0.5, "distance_km": 10.0, "candidate_score": 0.9},
            {"situation_id": "high-fire", "situation_title": "High Fire", "priority_score": 0.7, "capability_id": "crew-1", "resource_name": "Crew Alpha", "resource_type": "wildland_fire_crew", "resource_group": "fire", "proposed_fraction": 0.4, "distance_km": 20.0, "candidate_score": 0.8},
        ],
        "unmet_situations": [],
        "competing_resources": {"crew-1": ["critical-fire", "high-fire"]},
        "remaining_capacity": {"crew-1": 0.1},
        "policy": {"proposal_only": True, "human_authorization_required": True, "does_not_cancel_or_reassign_existing_allocations": True, "higher_priority_situations_consume_shared_capacity_first": True},
    }

    summary = build_allocation_summary(plan)
    assert summary["overview"]["active_situations"] == 2
    assert summary["overview"]["resource_conflicts"] == 1
    assert summary["incident_priority"][0]["situation_id"] == "critical-fire"
    assert summary["resource_allocation"][0]["proposed_total_fraction"] == 0.9
    assert summary["resource_allocation"][0]["remaining_fraction"] == 0.1
    assert summary["conflicts"][0]["incident_count"] == 2
    assert summary["capability_gaps"][0]["missing_resource_groups"] == ["medical"]
    assert summary["decision_status"]["human_authorization_required"] is True
