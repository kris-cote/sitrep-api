from app.services.resource_optimizer import _capability_group, _desired_groups, _suggested_fraction


class DummyCapability:
    def __init__(self, resource_type, name, capabilities):
        self.resource_type = resource_type
        self.name = name
        self.capabilities = capabilities


class DummySituation:
    domain = "wildfire"
    title = "Competing wildfire"
    summary = "Wildfire threatening a community"


def test_capability_groups():
    assert _capability_group(DummyCapability("wildland_fire_crew", "Crew Alpha", ["suppression"])) == "fire"
    assert _capability_group(DummyCapability("helicopter", "Heli 1", ["aviation"])) == "air"
    assert _capability_group(DummyCapability("ambulance", "Medic 1", ["medical"])) == "medical"
    assert _capability_group(DummyCapability("reception_centre", "Shelter 1", ["evacuation"])) == "shelter"


def test_wildfire_response_package_groups():
    assert _desired_groups(DummySituation()) == ["fire", "air", "medical", "shelter"]


def test_fraction_is_bounded():
    for group in ["fire", "air", "medical", "shelter", "general"]:
        fraction = _suggested_fraction(0.9, group)
        assert 0.08 <= fraction <= 0.50
