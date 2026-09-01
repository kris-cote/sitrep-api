from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Set, Tuple

from sqlmodel import Session, select

from app.models.dependency import DependencyEdge


def analyze_dependency_cascade(
    session: Session,
    tenant_id: str,
    seed_type: str,
    seed_id: str,
    max_depth: int = 4,
) -> Dict[str, Any]:
    edges = list(session.exec(select(DependencyEdge).where(DependencyEdge.tenant_id == tenant_id)).all())

    adjacency: Dict[Tuple[str, str], List[DependencyEdge]] = {}
    for edge in edges:
        key = (edge.upstream_type, edge.upstream_id)
        adjacency.setdefault(key, []).append(edge)

    queue = deque([((seed_type, seed_id), 0, 1.0)])
    visited: Set[Tuple[str, str]] = {(seed_type, seed_id)}
    impacts: List[Dict[str, Any]] = []

    while queue:
        node, depth, inherited = queue.popleft()
        if depth >= max_depth:
            continue
        for edge in adjacency.get(node, []):
            downstream = (edge.downstream_type, edge.downstream_id)
            propagated = inherited * max(0.0, min(1.0, edge.confidence)) * max(0.0, min(1.0, edge.criticality))
            impacts.append({
                "depth": depth + 1,
                "upstream_type": edge.upstream_type,
                "upstream_id": edge.upstream_id,
                "downstream_type": edge.downstream_type,
                "downstream_id": edge.downstream_id,
                "relationship": edge.relationship,
                "edge_confidence": edge.confidence,
                "edge_criticality": edge.criticality,
                "propagated_impact_score": round(propagated, 4),
                "source_system": edge.source_system,
            })
            if downstream not in visited:
                visited.add(downstream)
                queue.append((downstream, depth + 1, propagated))

    impacts.sort(key=lambda item: (-item["propagated_impact_score"], item["depth"]))
    return {
        "seed": {"type": seed_type, "id": seed_id},
        "max_depth": max_depth,
        "affected_nodes": max(0, len(visited) - 1),
        "impact_paths": impacts,
        "note": "Cascade uses explicit dependency edges only; geographic proximity alone is not treated as a dependency.",
    }
