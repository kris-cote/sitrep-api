from app.services.ai_tool_registry import execute_tool, tool_catalog


def test_tool_catalog_distinguishes_read_only_and_mutating_tools():
    catalog = {item["name"]: item for item in tool_catalog()}
    assert catalog["situation_snapshot"]["mutates_state"] is False
    assert catalog["operational_forecast"]["mutates_state"] is False
    assert catalog["resource_optimizer"]["mutates_state"] is False
    assert catalog["exposure_enrichment"]["mutates_state"] is True
    assert catalog["infrastructure_impact"]["mutates_state"] is True


def test_mutating_tool_is_blocked_without_explicit_permission():
    result = execute_tool(
        None,
        tool_name="exposure_enrichment",
        arguments={"situation_id": "situation-1"},
        tenant_id="default",
        situation_id="situation-1",
        allow_mutating_tools=False,
    )
    assert result["status"] == "blocked"
    assert result["mutates_state"] is True
    assert "explicit" in result["reason"].lower()
