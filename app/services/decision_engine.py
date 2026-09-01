from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass
class ScoredOption:
    name: str
    description: str
    score: float
    confidence: float
    risk_score: float
    urgency_score: float
    resource_score: float
    reversibility_score: float
    policy_score: float
    expected_outcomes: List[str]
    assumptions: List[str]
    constraints: List[str]
    rationale: List[str]
    metadata: Dict[str, Any]


DEFAULT_WEIGHTS = {
    "confidence": 0.22,
    "risk": 0.24,
    "urgency": 0.18,
    "resources": 0.12,
    "reversibility": 0.10,
    "policy": 0.14,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _score(option: Dict[str, Any], weights: Dict[str, float]) -> ScoredOption:
    confidence = _clamp(option.get("confidence", 0.5))
    risk = _clamp(option.get("risk_score", 0.5))
    urgency = _clamp(option.get("urgency_score", 0.5))
    resources = _clamp(option.get("resource_score", 0.5))
    reversibility = _clamp(option.get("reversibility_score", 0.5))
    policy = _clamp(option.get("policy_score", 1.0))

    weighted = (
        confidence * weights["confidence"]
        + (1.0 - risk) * weights["risk"]
        + urgency * weights["urgency"]
        + resources * weights["resources"]
        + reversibility * weights["reversibility"]
        + policy * weights["policy"]
    )

    rationale = list(option.get("rationale", []))
    rationale.extend([
        f"confidence={confidence:.2f}",
        f"risk={risk:.2f}",
        f"urgency={urgency:.2f}",
        f"resource_feasibility={resources:.2f}",
        f"reversibility={reversibility:.2f}",
        f"policy_compliance={policy:.2f}",
    ])

    return ScoredOption(
        name=str(option["name"]),
        description=str(option.get("description", "")),
        score=round(weighted, 4),
        confidence=confidence,
        risk_score=risk,
        urgency_score=urgency,
        resource_score=resources,
        reversibility_score=reversibility,
        policy_score=policy,
        expected_outcomes=list(option.get("expected_outcomes", [])),
        assumptions=list(option.get("assumptions", [])),
        constraints=list(option.get("constraints", [])),
        rationale=rationale,
        metadata=dict(option.get("metadata", {})),
    )


def rank_courses_of_action(
    options: Iterable[Dict[str, Any]],
    weights: Dict[str, float] | None = None,
) -> List[ScoredOption]:
    effective = dict(DEFAULT_WEIGHTS)
    if weights:
        effective.update({k: float(v) for k, v in weights.items() if k in effective})

    total = sum(effective.values())
    if total <= 0:
        raise ValueError("Decision weights must sum to a positive value")
    effective = {k: v / total for k, v in effective.items()}

    scored = [_score(option, effective) for option in options]
    return sorted(scored, key=lambda item: item.score, reverse=True)


def policy_flags(options: Iterable[ScoredOption]) -> List[str]:
    flags: List[str] = []
    for option in options:
        if option.policy_score < 0.5:
            flags.append(f"{option.name}: policy score below authorization threshold")
        if option.risk_score >= 0.85:
            flags.append(f"{option.name}: very high assessed risk")
    return flags


def risk_label(options: List[ScoredOption]) -> str:
    if not options:
        return "unknown"
    risk = options[0].risk_score
    if risk >= 0.8:
        return "critical"
    if risk >= 0.6:
        return "high"
    if risk >= 0.35:
        return "moderate"
    return "low"
