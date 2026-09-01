from app.services.ai_gateway import AIEvidenceContract, AIProvider, provider_allows


def test_classification_boundary_blocks_public_provider_for_protected_data():
    public = AIProvider(provider_id="p", name="Public", base_url="http://example", model="m", max_classification="public")
    assert provider_allows(public, "public")
    assert not provider_allows(public, "protected-b")


def test_sovereign_provider_can_be_classified_for_protected_b():
    canadian = AIProvider(provider_id="ca", name="Canadian", base_url="http://example", model="m", sovereign=True, jurisdiction="CA", max_classification="protected-b")
    assert provider_allows(canadian, "protected-a")
    assert provider_allows(canadian, "protected-b")
    assert not provider_allows(canadian, "secret")


def test_evidence_contract_bounds_confidence_and_keeps_authorization_policy():
    contract = AIEvidenceContract(summary="test", confidence=2.0).to_dict()
    assert contract["confidence"] == 1.0
    assert contract["policy"]["advisory_only"] is True
    assert contract["policy"]["human_authorization_required_for_consequential_actions"] is True
