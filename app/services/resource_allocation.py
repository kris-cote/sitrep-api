from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.models.resource_allocation import ResponseResourceAllocation
from app.models.resource_capability import ResponseResourceCapability

ACTIVE_STATUSES = {"planned", "active"}
FINAL_STATUSES = {"completed", "cancelled"}
ALL_STATUSES = ACTIVE_STATUSES | FINAL_STATUSES


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _overlaps(a_start: Optional[datetime], a_end: Optional[datetime], b_start: Optional[datetime], b_end: Optional[datetime]) -> bool:
    start_a = a_start or datetime.min.replace(tzinfo=timezone.utc)
    end_a = a_end or datetime.max.replace(tzinfo=timezone.utc)
    start_b = b_start or datetime.min.replace(tzinfo=timezone.utc)
    end_b = b_end or datetime.max.replace(tzinfo=timezone.utc)
    return start_a < end_b and start_b < end_a


def active_allocations(session: Session, capability_id: str, starts_at: Optional[datetime] = None, ends_at: Optional[datetime] = None, exclude_id: Optional[str] = None) -> List[ResponseResourceAllocation]:
    items = list(session.exec(select(ResponseResourceAllocation).where(ResponseResourceAllocation.capability_id == capability_id)).all())
    result = []
    for item in items:
        if item.id == exclude_id or item.status not in ACTIVE_STATUSES:
            continue
        if _overlaps(item.starts_at, item.ends_at, starts_at, ends_at):
            result.append(item)
    return result


def allocation_summary(session: Session, capability_id: str, starts_at: Optional[datetime] = None, ends_at: Optional[datetime] = None) -> Dict[str, Any]:
    cap = session.get(ResponseResourceCapability, capability_id)
    if not cap:
        raise ValueError("Resource capability not found")
    allocations = active_allocations(session, capability_id, starts_at=starts_at, ends_at=ends_at)
    committed = sum(max(0.0, min(1.0, float(item.allocated_fraction))) for item in allocations)
    remaining = max(0.0, 1.0 - committed)
    conflicts = committed > 1.000001
    return {
        "capability_id": capability_id,
        "resource_type": cap.resource_type,
        "availability_status": cap.availability_status,
        "committed_fraction": round(committed, 4),
        "remaining_fraction": round(remaining, 4),
        "overcommitted": conflicts,
        "active_allocation_count": len(allocations),
        "allocations": [
            {
                "allocation_id": item.id,
                "situation_id": item.situation_id,
                "decision_id": item.decision_id,
                "coa_id": item.coa_id,
                "assignment_name": item.assignment_name,
                "status": item.status,
                "allocated_fraction": item.allocated_fraction,
                "priority": item.priority,
                "starts_at": item.starts_at,
                "ends_at": item.ends_at,
            }
            for item in sorted(allocations, key=lambda x: (-x.priority, x.created_at))
        ],
    }


def _sync_capability_status(session: Session, cap: ResponseResourceCapability) -> Dict[str, Any]:
    summary = allocation_summary(session, cap.id)
    committed = float(summary["committed_fraction"])
    # Do not override explicit unavailable/maintenance states.
    current = (cap.availability_status or "unknown").lower()
    if current not in {"unavailable", "maintenance"}:
        if committed >= 0.95:
            cap.availability_status = "committed"
            cap.availability_score = min(float(cap.availability_score), 0.25)
        elif committed >= 0.60:
            cap.availability_status = "limited"
            cap.availability_score = min(float(cap.availability_score), max(0.35, 1.0 - committed))
        elif current in {"committed", "limited"}:
            cap.availability_status = "available"
            cap.availability_score = max(float(cap.availability_score), 0.75)
    cap.updated_at = utcnow()
    session.add(cap)
    return summary


def create_allocation(
    session: Session,
    capability_id: str,
    assignment_name: str,
    requested_fraction: float,
    allocated_fraction: float,
    tenant_id: str = "default",
    situation_id: Optional[str] = None,
    decision_id: Optional[str] = None,
    coa_id: Optional[str] = None,
    priority: int = 50,
    starts_at: Optional[datetime] = None,
    ends_at: Optional[datetime] = None,
    constraints: Optional[Dict[str, Any]] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
    created_by: str = "operator",
    allow_overcommit: bool = False,
) -> Dict[str, Any]:
    cap = session.get(ResponseResourceCapability, capability_id)
    if not cap:
        raise ValueError("Resource capability not found")
    if cap.tenant_id != tenant_id:
        raise ValueError("Resource capability tenant mismatch")
    if requested_fraction < 0 or requested_fraction > 1 or allocated_fraction < 0 or allocated_fraction > 1:
        raise ValueError("requested_fraction and allocated_fraction must be between 0 and 1")
    if starts_at and ends_at and ends_at <= starts_at:
        raise ValueError("ends_at must be after starts_at")
    before = allocation_summary(session, capability_id, starts_at=starts_at, ends_at=ends_at)
    projected = float(before["committed_fraction"]) + float(allocated_fraction)
    conflict = projected > 1.000001
    if conflict and not allow_overcommit:
        raise ValueError(f"Allocation would overcommit capability: projected_fraction={projected:.4f}")
    record = ResponseResourceAllocation(
        tenant_id=tenant_id,
        capability_id=capability_id,
        situation_id=situation_id,
        decision_id=decision_id,
        coa_id=coa_id,
        assignment_name=assignment_name,
        status="planned",
        requested_fraction=requested_fraction,
        allocated_fraction=allocated_fraction,
        priority=max(0, min(100, int(priority))),
        starts_at=starts_at,
        ends_at=ends_at,
        constraints=constraints or {},
        metadata_json=metadata_json or {},
        created_by=created_by,
    )
    session.add(record)
    session.flush()
    summary = _sync_capability_status(session, cap)
    session.commit()
    session.refresh(record)
    return {
        "allocation": record,
        "conflict_detected": conflict,
        "projected_fraction": round(projected, 4),
        "capability_summary": allocation_summary(session, capability_id, starts_at=starts_at, ends_at=ends_at),
    }


def update_allocation_status(session: Session, allocation_id: str, status: str) -> ResponseResourceAllocation:
    normalized = status.lower().strip()
    if normalized not in ALL_STATUSES:
        raise ValueError(f"Unsupported allocation status: {status}")
    item = session.get(ResponseResourceAllocation, allocation_id)
    if not item:
        raise ValueError("Resource allocation not found")
    item.status = normalized
    item.updated_at = utcnow()
    session.add(item)
    cap = session.get(ResponseResourceCapability, item.capability_id)
    if cap:
        _sync_capability_status(session, cap)
    session.commit()
    session.refresh(item)
    return item
