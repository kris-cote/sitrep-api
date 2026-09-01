from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.models.resource_allocation import ResponseResourceAllocation
from app.models.resource_capability import ResponseResourceCapability
from app.models.situation import SituationRecord
from app.services.resource_allocation import ACTIVE_STATUSES
from app.services.resource_optimizer import _situation_priority

DEFAULT_HORIZONS_HOURS = [0.5, 2.0, 6.0, 24.0]

DOMAIN_RESOURCE_MIX: Dict[str, Dict[str, float]] = {
    "wildfire-emergency": {"fire": 0.90, "air": 0.70, "medical": 0.45, "shelter": 0.55, "general": 0.50},
    "canada-maritime-arctic": {"air": 0.65, "medical": 0.35, "general": 0.65},
    "critical-infrastructure": {"general": 0.75, "medical": 0.30, "shelter": 0.30},
    "general": {"general": 0.60, "medical": 0.30, "shelter": 0.25},
}


def _domain_mix(domain: str) -> Dict[str, float]:
    return DOMAIN_RESOURCE_MIX.get((domain or "general").lower(), DOMAIN_RESOURCE_MIX["general"])


def _trend_signal(situation: SituationRecord) -> float:
    """Return a bounded forecast trend from explicit situation context only.

    Positive values indicate expected worsening; negative values indicate expected easing.
    If no explicit trend evidence exists, return zero rather than guessing.
    """
    context = situation.context or {}
    explicit = context.get("forecast_trend")
    if isinstance(explicit, (int, float)):
        return max(-1.0, min(1.0, float(explicit)))
    text = " ".join([
        str(context.get("trend") or ""),
        str(context.get("forecast") or ""),
        " ".join(str(x) for x in situation.correlation_reasons or []),
    ]).lower()
    worsening = sum(1 for term in ("worsening", "increasing", "spreading", "intensifying", "escalating", "strong wind", "high wind") if term in text)
    easing = sum(1 for term in ("improving", "decreasing", "contained", "stabilizing", "easing") if term in text)
    if worsening == easing == 0:
        return 0.0
    return max(-1.0, min(1.0, 0.20 * (worsening - easing)))


def _forecast_priority(situation: SituationRecord, horizon_hours: float) -> Dict[str, float]:
    current = _situation_priority(situation)
    trend = _trend_signal(situation)
    # Influence grows with horizon but is intentionally capped because this is a
    # screening forecast, not a validated hazard-prediction model.
    horizon_factor = min(1.0, horizon_hours / 12.0)
    delta = 0.30 * trend * horizon_factor
    forecast = max(0.0, min(1.0, current + delta))
    uncertainty = min(0.55, 0.12 + 0.018 * horizon_hours)
    return {
        "current_priority": round(current, 4),
        "forecast_priority": round(forecast, 4),
        "trend_signal": round(trend, 4),
        "uncertainty": round(uncertainty, 4),
    }


def _resource_group(cap: ResponseResourceCapability) -> str:
    text = " ".join([cap.resource_type or "", cap.name or "", " ".join(cap.capabilities or [])]).lower()
    if any(term in text for term in ("aircraft", "aviation", "helicopter", "rotary", "fixed wing", "airbase")):
        return "air"
    if any(term in text for term in ("fire", "suppression", "engine", "crew")):
        return "fire"
    if any(term in text for term in ("medical", "ambulance", "hospital", "medevac")):
        return "medical"
    if any(term in text for term in ("shelter", "reception")):
        return "shelter"
    return "general"


def forecast_operational_demand(
    session: Session,
    tenant_id: str = "default",
    horizons_hours: Optional[List[float]] = None,
    max_situations: int = 100,
) -> Dict[str, Any]:
    horizons = sorted({float(h) for h in (horizons_hours or DEFAULT_HORIZONS_HOURS) if float(h) > 0})
    situations = list(session.exec(
        select(SituationRecord)
        .where(SituationRecord.tenant_id == tenant_id)
        .where(SituationRecord.status == "active")
        .order_by(SituationRecord.updated_at.desc())
        .limit(max_situations)
    ).all())
    capabilities = list(session.exec(
        select(ResponseResourceCapability).where(ResponseResourceCapability.tenant_id == tenant_id)
    ).all())
    allocations = list(session.exec(
        select(ResponseResourceAllocation).where(ResponseResourceAllocation.tenant_id == tenant_id)
    ).all())

    committed_by_cap: Dict[str, float] = {}
    for allocation in allocations:
        if allocation.status in ACTIVE_STATUSES:
            committed_by_cap[allocation.capability_id] = committed_by_cap.get(allocation.capability_id, 0.0) + max(0.0, min(1.0, float(allocation.allocated_fraction)))

    supply: Dict[str, float] = {"air": 0.0, "fire": 0.0, "medical": 0.0, "shelter": 0.0, "general": 0.0}
    for cap in capabilities:
        group = _resource_group(cap)
        remaining = max(0.0, 1.0 - committed_by_cap.get(cap.id, 0.0))
        readiness = max(0.0, min(1.0, float(cap.readiness_score)))
        suitability = max(0.0, min(1.0, float(cap.suitability_score)))
        availability = max(0.0, min(1.0, float(cap.availability_score)))
        supply[group] += remaining * readiness * suitability * availability
        if group != "general":
            supply["general"] += 0.25 * remaining * readiness * suitability * availability

    horizon_results: List[Dict[str, Any]] = []
    for horizon in horizons:
        demand: Dict[str, float] = {"air": 0.0, "fire": 0.0, "medical": 0.0, "shelter": 0.0, "general": 0.0}
        situation_forecasts: List[Dict[str, Any]] = []
        for situation in situations:
            forecast = _forecast_priority(situation, horizon)
            priority = float(forecast["forecast_priority"])
            mix = _domain_mix(situation.domain)
            for group, weight in mix.items():
                demand[group] += priority * float(weight)
            situation_forecasts.append({
                "situation_id": situation.id,
                "title": situation.title,
                "domain": situation.domain,
                "severity": situation.severity,
                **forecast,
            })

        groups: Dict[str, Any] = {}
        shortages: List[Dict[str, Any]] = []
        for group in demand:
            available = float(supply.get(group, 0.0))
            required = float(demand[group])
            gap = required - available
            utilization = required / available if available > 0 else (999.0 if required > 0 else 0.0)
            groups[group] = {
                "forecast_demand_units": round(required, 4),
                "available_effective_units": round(available, 4),
                "gap_units": round(gap, 4),
                "forecast_utilization": round(min(utilization, 999.0), 4),
            }
            if gap > 0.10:
                shortages.append({"resource_group": group, "gap_units": round(gap, 4)})

        staging = sorted(shortages, key=lambda x: -x["gap_units"])
        horizon_results.append({
            "horizon_hours": horizon,
            "groups": groups,
            "shortages": staging,
            "staging_recommendations": [
                {
                    "resource_group": item["resource_group"],
                    "recommended_action": "identify additional capacity or pre-stage available resources",
                    "forecast_gap_units": item["gap_units"],
                    "requires_human_authorization": True,
                }
                for item in staging[:5]
            ],
            "situations": sorted(situation_forecasts, key=lambda x: -float(x["forecast_priority"])),
        })

    return {
        "generated_at": datetime.now(timezone.utc),
        "tenant_id": tenant_id,
        "active_situation_count": len(situations),
        "capability_count": len(capabilities),
        "active_allocation_count": sum(1 for a in allocations if a.status in ACTIVE_STATUSES),
        "effective_supply_units": {k: round(v, 4) for k, v in supply.items()},
        "horizons": horizon_results,
        "policy": {
            "screening_forecast_only": True,
            "proposal_only": True,
            "human_authorization_required": True,
            "uses_explicit_trend_evidence_when_available": True,
            "does_not_execute_staging_or_reallocation": True,
        },
        "limitations": [
            "Forecast priority is a bounded screening estimate, not a validated hazard-behaviour model.",
            "Unknown future changes are represented through growing uncertainty with forecast horizon.",
            "Resource demand coefficients are mission-pack heuristics and should be calibrated with operator data.",
        ],
    }
