from datetime import datetime, timedelta, timezone

from app.models.resource_allocation import ResponseResourceAllocation
from app.services.resource_allocation import _overlaps
from app.services.resource_availability import _capability_score


class DummyCapability:
    availability_status = "available"
    availability_score = 1.0
    readiness_score = 1.0
    capacity_score = 1.0
    suitability_score = 1.0
    valid_from = None
    valid_until = None


def test_allocation_pressure_reduces_capability_score():
    cap = DummyCapability()
    idle = _capability_score(cap, committed_fraction=0.0)
    mostly_committed = _capability_score(cap, committed_fraction=0.9)
    fully_committed = _capability_score(cap, committed_fraction=1.0)
    assert idle > mostly_committed > fully_committed


def test_allocation_time_windows_overlap_correctly():
    now = datetime.now(timezone.utc)
    assert _overlaps(now, now + timedelta(hours=2), now + timedelta(hours=1), now + timedelta(hours=3))
    assert not _overlaps(now, now + timedelta(hours=1), now + timedelta(hours=1), now + timedelta(hours=2))
