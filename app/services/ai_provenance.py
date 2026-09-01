from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import Session

from app.models.ai_provenance import AIProvenanceRecord


def _fingerprint(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def record_ai_run(
    session: Session,
    *,
    role: str,
    request_payload: Dict[str, Any],
    response_payload: Dict[str, Any],
    tenant_id: str = "default",
    mission_id: Optional[str] = None,
    situation_id: Optional[str] = None,
    decision_id: Optional[str] = None,
    parent_run_id: Optional[str] = None,
    data_classification: str = "public",
    sovereign_required: bool = False,
    agent_version: str = "1.0",
    input_refs: Optional[List[Dict[str, Any]]] = None,
) -> AIProvenanceRecord:
    analysis = response_payload.get("analysis") or response_payload.get("red_team") or response_payload
    record = AIProvenanceRecord(
        tenant_id=tenant_id,
        mission_id=mission_id,
        situation_id=situation_id,
        decision_id=decision_id,
        parent_run_id=parent_run_id,
        role=role,
        agent_version=agent_version,
        provider_id=response_payload.get("model_provider") or analysis.get("model_provider"),
        model_name=response_payload.get("model_name") or analysis.get("model_name"),
        data_classification=data_classification,
        sovereign_required=sovereign_required,
        prompt_fingerprint=_fingerprint(request_payload),
        input_refs=input_refs or [],
        request_payload=request_payload,
        response_payload=response_payload,
        evidence=list(analysis.get("evidence") or []),
        assumptions=[str(x) for x in analysis.get("assumptions") or []],
        contradictions=[str(x) for x in analysis.get("contradictions") or []],
        information_gaps=[str(x) for x in analysis.get("information_gaps") or response_payload.get("information_gaps") or []],
        confidence=max(0.0, min(1.0, float(analysis.get("confidence") or response_payload.get("confidence") or 0.5))),
        advisory_only=True,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def record_ai_error(
    session: Session,
    *,
    role: str,
    request_payload: Dict[str, Any],
    error: str,
    tenant_id: str = "default",
    situation_id: Optional[str] = None,
    data_classification: str = "public",
    sovereign_required: bool = False,
) -> AIProvenanceRecord:
    record = AIProvenanceRecord(
        tenant_id=tenant_id,
        situation_id=situation_id,
        role=role,
        data_classification=data_classification,
        sovereign_required=sovereign_required,
        prompt_fingerprint=_fingerprint(request_payload),
        request_payload=request_payload,
        response_payload={},
        status="error",
        error=error,
        advisory_only=True,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def set_operator_action(session: Session, run_id: str, action: str, actor: str, note: str = "") -> AIProvenanceRecord:
    record = session.get(AIProvenanceRecord, run_id)
    if not record:
        raise ValueError("AI provenance record not found")
    record.operator_action = action
    record.operator_actor = actor
    record.operator_note = note
    record.operator_action_at = datetime.now(timezone.utc)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
