from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlmodel import Session

from app.models.decision import CourseOfAction, DecisionAudit, DecisionRecord
from app.services.scenario_comparison import compare_scenarios


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _risk_level(avg_priority: float) -> str:
    if avg_priority >= 0.80:
        return "critical"
    if avg_priority >= 0.60:
        return "high"
    if avg_priority >= 0.35:
        return "moderate"
    return "low"


def promote_scenario_comparison(
    session: Session,
    *,
    situation_id: str,
    branches: List[Dict[str, Any]],
    selected_branch_id: Optional[str] = None,
    tenant_id: str = "default",
    mission_id: Optional[str] = None,
    domain: str = "general",
    title: str = "Scenario planning decision",
    summary: str = "",
    horizons_hours: Optional[List[float]] = None,
    weights: Optional[Dict[str, float]] = None,
    actor: str = "operator",
) -> Dict[str, Any]:
    comparison = compare_scenarios(
        session=session,
        branches=branches,
        tenant_id=tenant_id,
        horizons_hours=horizons_hours,
        weights=weights,
    )

    ranked = comparison["ranked_scenarios"]
    if not ranked:
        raise ValueError("Scenario comparison produced no ranked branches")

    selected_id = selected_branch_id or comparison["recommended_branch_id"]
    selected = next((item for item in ranked if item["branch_id"] == selected_id), None)
    if not selected:
        raise ValueError(f"Selected branch not found: {selected_id}")

    selected_sim = selected.get("simulation") or {}
    selected_situations = selected_sim.get("scenario", {}).get("situations", []) or []
    avg_priority = 0.0
    if selected_situations:
        avg_priority = sum(float(item.get("scenario_priority") or 0.0) for item in selected_situations) / len(selected_situations)

    decision = DecisionRecord(
        mission_id=mission_id,
        situation_id=situation_id,
        domain=domain,
        title=title,
        summary=summary or f"Promoted scenario comparison; selected branch: {selected['name']}",
        confidence=_bounded(float(selected.get("metrics", {}).get("confidence") or 0.5)),
        risk_level=_risk_level(avg_priority),
        policy_flags=["scenario-derived", "human-authorization-required"],
        evidence=[
            {
                "type": "scenario_comparison",
                "recommended_branch_id": comparison.get("recommended_branch_id"),
                "operator_selected_branch_id": selected_id,
                "weights": comparison.get("weights"),
                "ranked_summary": [
                    {
                        "branch_id": item["branch_id"],
                        "name": item["name"],
                        "rank": item["rank"],
                        "score": item["score"],
                        "metrics": item["metrics"],
                    }
                    for item in ranked
                ],
            }
        ],
        context={
            "source": "scenario-comparison",
            "tenant_id": tenant_id,
            "selected_branch_id": selected_id,
            "recommended_branch_id": comparison.get("recommended_branch_id"),
            "comparison_policy": comparison.get("policy"),
            "comparison_limitations": comparison.get("limitations"),
            "horizons_hours": horizons_hours,
        },
    )
    session.add(decision)
    session.flush()

    records: List[CourseOfAction] = []
    selected_record: Optional[CourseOfAction] = None
    for item in ranked:
        metrics = item.get("metrics") or {}
        simulation = item.get("simulation") or {}
        sim_situations = simulation.get("scenario", {}).get("situations", []) or []
        scenario_priority = 0.0
        if sim_situations:
            scenario_priority = sum(float(x.get("scenario_priority") or 0.0) for x in sim_situations) / len(sim_situations)

        shortages = []
        for horizon in simulation.get("scenario", {}).get("forecast", []) or []:
            for group_name, group in (horizon.get("groups") or {}).items():
                if group.get("shortage"):
                    shortages.append(f"{group_name} shortage at {horizon.get('horizon_hours')}h")

        branch_source = next((b for b in branches if str(b.get("branch_id")) == item["branch_id"]), {})
        assumptions = []
        assumptions.extend([f"situation_change:{x}" for x in branch_source.get("situation_changes", [])])
        assumptions.extend([f"resource_change:{x}" for x in branch_source.get("resource_changes", [])])
        assumptions.extend([f"infrastructure_change:{x}" for x in branch_source.get("infrastructure_changes", [])])

        record = CourseOfAction(
            decision_id=decision.id,
            name=item["name"],
            description=item.get("description") or "Scenario-derived course of action",
            rank=int(item["rank"]),
            score=_bounded(float(item["score"])),
            confidence=_bounded(float(metrics.get("confidence") or 0.5)),
            risk_score=_bounded(scenario_priority),
            urgency_score=_bounded(scenario_priority),
            resource_score=_bounded(float(metrics.get("resource_efficiency") or 0.5)),
            reversibility_score=_bounded(float(metrics.get("reversibility") or 0.5)),
            policy_score=1.0,
            expected_outcomes=[
                f"risk_reduction={float(metrics.get('risk_reduction') or 0.0):.4f}",
                f"operational_continuity={float(metrics.get('operational_continuity') or 0.0):.4f}",
            ],
            assumptions=assumptions,
            constraints=shortages,
            rationale=[
                f"scenario_rank={item['rank']}",
                f"comparison_score={float(item['score']):.4f}",
                f"resource_efficiency={float(metrics.get('resource_efficiency') or 0.0):.4f}",
                f"reversibility={float(metrics.get('reversibility') or 0.0):.4f}",
                f"confidence={float(metrics.get('confidence') or 0.0):.4f}",
            ],
            metadata_json={
                "branch_id": item["branch_id"],
                "scenario_metrics": metrics,
                "simulation": simulation,
                "operator_selected": item["branch_id"] == selected_id,
                "engine_recommended": item["branch_id"] == comparison.get("recommended_branch_id"),
            },
        )
        session.add(record)
        records.append(record)
        if item["branch_id"] == selected_id:
            selected_record = record

    session.flush()
    if not selected_record:
        raise ValueError("Selected scenario branch could not be converted into a course of action")

    decision.recommended_option_id = selected_record.id
    session.add(decision)
    session.add(
        DecisionAudit(
            decision_id=decision.id,
            action="scenario_promoted",
            actor=actor,
            payload={
                "selected_branch_id": selected_id,
                "engine_recommended_branch_id": comparison.get("recommended_branch_id"),
                "selected_option_id": selected_record.id,
                "branch_count": len(records),
                "requires_human_authorization": True,
            },
        )
    )
    session.commit()
    session.refresh(decision)

    return {
        "decision_id": decision.id,
        "situation_id": decision.situation_id,
        "status": decision.status,
        "selected_branch_id": selected_id,
        "engine_recommended_branch_id": comparison.get("recommended_branch_id"),
        "recommended_option_id": decision.recommended_option_id,
        "recommended_option": selected_record.name,
        "course_of_action_count": len(records),
        "requires_human_authorization": decision.requires_human_authorization,
        "comparison": comparison,
    }
