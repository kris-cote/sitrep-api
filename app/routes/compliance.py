from __future__ import annotations



from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.dependencies import AsyncSessionLocal
from app.services.compliance_engine import (
    decision_to_dict,
    evaluate_compliance,
    get_active_policy,
)

router = APIRouter(prefix="/api/v1", tags=["compliance"])


class ComplianceEvaluateRequest(BaseModel):
    tenant_id: str = "default"
    source_system: str = Field(..., examples=["sigint_sim"])
    source_type: str = Field(..., examples=["sigint"])
    classification_in: str = Field("UNCLASSIFIED", examples=["PROTECTED_B"])
    security_domain_in: str = Field("open_network", examples=["mission_network"])
    requested_output_domain: str = Field("operator_console", examples=["operator_console"])
    output_audience: str = "operator_console"
    observation_id: Optional[str] = None
    entity_id: Optional[str] = None
    fusion_output_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.get("/policies/active")
async def read_active_policy():
    return {
        "status": "ok",
        "policy": get_active_policy(),
    }


@router.post("/compliance/evaluate")
async def evaluate_compliance_endpoint(payload: ComplianceEvaluateRequest):
    decision = evaluate_compliance(
        source_system=payload.source_system,
        source_type=payload.source_type,
        classification_in=payload.classification_in,
        security_domain_in=payload.security_domain_in,
        requested_output_domain=payload.requested_output_domain,
        output_audience=payload.output_audience,
        metadata=payload.metadata,
    )

    decision_dict = decision_to_dict(decision)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO compliance_audit_logs (
                    tenant_id,
                    observation_id,
                    entity_id,
                    fusion_output_id,
                    policy_id,
                    policy_version,
                    rule_id,
                    source_system,
                    source_type,
                    classification_in,
                    classification_out,
                    security_domain_in,
                    requested_output_domain,
                    enforcement_action,
                    compliance_disposition,
                    reason,
                    human_readable_decision,
                    machine_readable_policy,
                    evidence
                )
                VALUES (
                    :tenant_id,
                    :observation_id,
                    :entity_id,
                    :fusion_output_id,
                    :policy_id,
                    :policy_version,
                    :rule_id,
                    :source_system,
                    :source_type,
                    :classification_in,
                    :classification_out,
                    :security_domain_in,
                    :requested_output_domain,
                    :enforcement_action,
                    :compliance_disposition,
                    :reason,
                    :human_readable_decision,
                    CAST(:machine_readable_policy AS jsonb),
                    CAST(:evidence AS jsonb)
                )
                RETURNING id, created_at
                """
            ),
            {
                "tenant_id": payload.tenant_id,
                "observation_id": payload.observation_id,
                "entity_id": payload.entity_id,
                "fusion_output_id": payload.fusion_output_id,
                "policy_id": decision.policy_id,
                "policy_version": decision.policy_version,
                "rule_id": decision.rule_id,
                "source_system": decision.source_system,
                "source_type": decision.source_type,
                "classification_in": decision.classification_in,
                "classification_out": decision.classification_out,
                "security_domain_in": decision.security_domain_in,
                "requested_output_domain": decision.requested_output_domain,
                "enforcement_action": decision.enforcement_action,
                "compliance_disposition": decision.compliance_disposition,
                "reason": decision.reason,
                "human_readable_decision": decision.human_readable_decision,
                "machine_readable_policy": __import__("json").dumps(decision.machine_readable_policy),
                "evidence": __import__("json").dumps(decision.evidence),
            },
        )
        row = result.mappings().one()
        await session.commit()

        return {
            "status": "ok",
            "tenant_id": payload.tenant_id,
            "audit_log_id": str(row["id"]),
            "audit_created_at": row["created_at"].isoformat(),
            "decision": decision_dict,
        }


@router.get("/compliance/audit")
async def read_compliance_audit(
    tenant_id: str = Query("default"),
    limit: int = Query(100, ge=1, le=500),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    id,
                    tenant_id,
                    observation_id,
                    entity_id,
                    fusion_output_id,
                    policy_id,
                    policy_version,
                    rule_id,
                    source_system,
                    source_type,
                    classification_in,
                    classification_out,
                    security_domain_in,
                    requested_output_domain,
                    enforcement_action,
                    compliance_disposition,
                    reason,
                    human_readable_decision,
                    machine_readable_policy,
                    evidence,
                    created_at
                FROM compliance_audit_logs
                WHERE tenant_id = :tenant_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"tenant_id": tenant_id, "limit": limit},
        )

        rows = []
        for r in result.mappings().all():
            item = dict(r)
            for k in ["id", "observation_id", "entity_id", "fusion_output_id"]:
                if item.get(k) is not None:
                    item[k] = str(item[k])
            if item.get("created_at") is not None:
                item["created_at"] = item["created_at"].isoformat()
            rows.append(item)

        return {
            "status": "ok",
            "tenant_id": tenant_id,
            "count": len(rows),
            "audit_logs": rows,
        }


@router.get("/compliance/audit/export")
async def export_compliance_audit(
    tenant_id: str = Query("default"),
    limit: int = Query(500, ge=1, le=2000),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    id,
                    tenant_id,
                    observation_id,
                    entity_id,
                    fusion_output_id,
                    policy_id,
                    policy_version,
                    rule_id,
                    source_system,
                    source_type,
                    classification_in,
                    classification_out,
                    security_domain_in,
                    requested_output_domain,
                    enforcement_action,
                    compliance_disposition,
                    reason,
                    human_readable_decision,
                    machine_readable_policy,
                    evidence,
                    created_at
                FROM compliance_audit_logs
                WHERE tenant_id = :tenant_id
                ORDER BY created_at ASC
                LIMIT :limit
                """
            ),
            {"tenant_id": tenant_id, "limit": limit},
        )

        records = []
        for r in result.mappings().all():
            item = dict(r)
            for k in ["id", "observation_id", "entity_id", "fusion_output_id"]:
                if item.get(k) is not None:
                    item[k] = str(item[k])
            if item.get("created_at") is not None:
                item["created_at"] = item["created_at"].isoformat()
            records.append(item)

        return {
            "status": "ok",
            "export_type": "sitrep_fce_compliance_audit_json",
            "tenant_id": tenant_id,
            "record_count": len(records),
            "records": records,
        }
