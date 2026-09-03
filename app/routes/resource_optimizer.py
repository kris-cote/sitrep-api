from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.models.db import get_session
from app.models.decision import CourseOfAction, DecisionAudit, DecisionRecord
from app.services.allocation_summary import build_allocation_summary
from app.services.resource_optimizer import optimize_resource_plan

router = APIRouter(prefix="/resource-optimizer", tags=["resource-optimizer"])


def _plan(
    session: Session,
    tenant_id: str,
    max_distance_km: float,
    max_situations: int,
    max_candidates_per_situation: int,
):
    return optimize_resource_plan(
        session=session,
        tenant_id=tenant_id,
        max_distance_km=max_distance_km,
        max_situations=max_situations,
        max_candidates_per_situation=max_candidates_per_situation,
    )


@router.get("/plan")
def get_resource_optimization_plan(
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    max_distance_km: float = Query(default=300.0, gt=0, le=2000),
    max_situations: int = Query(default=100, ge=1, le=500),
    max_candidates_per_situation: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
):
    return _plan(session, tenant_id, max_distance_km, max_situations, max_candidates_per_situation)


@router.get("/summary")
def get_resource_allocation_summary(
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    max_distance_km: float = Query(default=300.0, gt=0, le=2000),
    max_situations: int = Query(default=100, ge=1, le=500),
    max_candidates_per_situation: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
):
    """Dashboard-ready decision summary: priorities, allocations, gaps and conflicts."""
    plan = _plan(session, tenant_id, max_distance_km, max_situations, max_candidates_per_situation)
    return build_allocation_summary(plan)


@router.post("/decision-proposal", status_code=201)
def create_resource_decision_proposal(
    tenant_id: str = Query(default="default", min_length=1, max_length=128),
    max_distance_km: float = Query(default=300.0, gt=0, le=2000),
    max_situations: int = Query(default=100, ge=1, le=500),
    max_candidates_per_situation: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
):
    """Persist the current optimization result as an operator decision proposal.

    This never creates dispatch/allocation records. Approval remains an explicit human action.
    """
    plan = _plan(session, tenant_id, max_distance_km, max_situations, max_candidates_per_situation)
    summary = build_allocation_summary(plan)
    incidents = summary.get("incident_priority") or []
    if not incidents:
        raise HTTPException(status_code=400, detail="No active situations are available for a resource decision")

    lead = incidents[0]
    conflicts = summary.get("conflicts") or []
    gaps = summary.get("capability_gaps") or []
    resources = summary.get("resource_allocation") or []
    package_confidence = float(lead.get("package_confidence") or 0.0)
    package_score = float(lead.get("package_score") or 0.0)
    priority_score = float(lead.get("priority_score") or 0.0)

    decision = DecisionRecord(
        situation_id=lead["situation_id"],
        domain="resource-allocation",
        title=f"Resource allocation proposal: {lead.get('title')}",
        summary=(
            f"SitRep recommends a multi-incident resource plan covering {summary['overview']['active_situations']} active situations, "
            f"{summary['overview']['proposed_allocations']} proposed allocations and {summary['overview']['resource_conflicts']} shared-resource conflicts."
        ),
        status="proposed",
        confidence=package_confidence,
        risk_level="high" if conflicts or gaps else "moderate",
        requires_human_authorization=True,
        policy_flags=[
            "recommendation_only",
            "human_authorization_required",
            "does_not_dispatch_resources",
            "preserve_existing_allocations",
            "priority_ordering_applied",
        ],
        evidence=[{
            "type": "deterministic_resource_optimizer",
            "source": "sitrep-resource-optimizer",
            "active_situations": summary["overview"]["active_situations"],
            "proposed_allocations": summary["overview"]["proposed_allocations"],
            "resource_conflicts": summary["overview"]["resource_conflicts"],
            "capability_gaps": summary["overview"]["capability_gaps"],
        }],
        context={
            "allocation_summary": summary,
            "optimizer_plan": plan,
            "operator_workflow": "approve_modify_or_reject",
            "dispatch_effect": "none",
        },
    )
    session.add(decision)
    session.flush()

    approve = CourseOfAction(
        decision_id=decision.id,
        name="Approve recommended resource plan",
        description="Accept the optimizer's current priority ordering and proposed resource fractions for planning purposes.",
        rank=1,
        score=package_score,
        confidence=package_confidence,
        risk_score=max(0.0, min(1.0, 1.0 - package_score)),
        urgency_score=priority_score,
        resource_score=package_score,
        reversibility_score=0.85,
        policy_score=1.0,
        expected_outcomes=["Record the recommended plan as human-approved", "Preserve complete decision audit history"],
        assumptions=["Current capability availability remains valid until the next optimization run"],
        constraints=["Approval does not dispatch, task, or reassign any real-world resource"],
        rationale=["Highest-priority incidents consume shared capacity first", f"{len(conflicts)} resource conflicts identified", f"{len(gaps)} capability gaps identified"],
        metadata_json={"allocation_summary": summary},
    )
    modify = CourseOfAction(
        decision_id=decision.id,
        name="Modify and rebalance resource plan",
        description="Operator changes resource fractions, priorities, or selected resources before approval.",
        rank=2,
        score=max(0.0, package_score - 0.05),
        confidence=max(0.0, package_confidence - 0.05),
        risk_score=0.30,
        urgency_score=priority_score,
        resource_score=0.75,
        reversibility_score=0.98,
        policy_score=1.0,
        expected_outcomes=["Capture operator changes without losing the original recommendation"],
        assumptions=["Operator has additional context unavailable to the optimizer"],
        constraints=["Modified recommendation still requires explicit approval"],
        rationale=["Use when local knowledge, policy or operational constraints justify a different allocation"],
        metadata_json={"modification_template": {"resource_overrides": [], "priority_overrides": [], "notes": ""}},
    )
    reject = CourseOfAction(
        decision_id=decision.id,
        name="Reject plan and reassess",
        description="Reject the current plan and request new data, resources, or another optimization run.",
        rank=3,
        score=max(0.0, package_score - 0.15),
        confidence=0.65,
        risk_score=0.55,
        urgency_score=priority_score,
        resource_score=0.60,
        reversibility_score=1.0,
        policy_score=1.0,
        expected_outcomes=["No recommendation is approved", "Plan can be regenerated after conditions change"],
        assumptions=["Current proposal is operationally unsuitable or insufficiently evidenced"],
        constraints=["Delay may increase incident risk for urgent situations"],
        rationale=["Use when the recommendation conflicts with authority, policy, safety, or updated field information"],
        metadata_json={},
    )
    for option in (approve, modify, reject):
        session.add(option)
    session.flush()
    decision.recommended_option_id = approve.id
    session.add(DecisionAudit(
        decision_id=decision.id,
        action="generated_from_resource_optimizer",
        actor="sitrep-resource-optimizer",
        payload={
            "recommended_option_id": approve.id,
            "active_situations": summary["overview"]["active_situations"],
            "proposed_allocations": summary["overview"]["proposed_allocations"],
            "resource_conflicts": summary["overview"]["resource_conflicts"],
        },
    ))
    session.commit()
    session.refresh(decision)

    return {
        "decision_id": decision.id,
        "status": decision.status,
        "title": decision.title,
        "recommended_option_id": decision.recommended_option_id,
        "requires_human_authorization": True,
        "dispatch_effect": "none",
        "actions": {
            "approve": f"/decisions/{decision.id}/approve",
            "modify": f"/decisions/{decision.id}/modify",
            "reject": f"/decisions/{decision.id}/reject",
            "explanation": f"/decisions/{decision.id}/explanation",
            "audit": f"/decisions/{decision.id}/audit",
        },
        "summary": summary,
    }
