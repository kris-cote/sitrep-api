# app/api/routers/integrations.py
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlmodel import Session

from app.models.db import get_session
from app.models.entities import Event
from app.models.schemas import EventRead
from app.core.security import verify_api_key

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


def _resolve_tenant(x_tenant_id: Optional[str]) -> Optional[UUID]:
    if not x_tenant_id:
        return None
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Tenant-Id header",
        )


@router.post("/webhook", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def generic_webhook(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
    x_mission_id: Optional[str] = Header(default=None, alias="X-Mission-Id"),
    x_source_system: Optional[str] = Header(default=None, alias="X-Source-System"),
    x_event_type: Optional[str] = Header(default=None, alias="X-Event-Type"),
):
    """
    Generic webhook endpoint for n8n/Make/ThingsBoard/FleetDM/etc.

    - Accepts arbitrary JSON body.
    - Uses headers to tag tenant, mission, source_system, event_type.
    """

    tenant_id = _resolve_tenant(x_tenant_id)

    mission_id: Optional[UUID] = None
    if x_mission_id:
        try:
            mission_id = UUID(x_mission_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Mission-Id header",
            )

    event = Event(
        tenant_id=tenant_id,
        mission_id=mission_id,
        event_type=x_event_type or "integration.webhook",
        source_system=x_source_system or "integration",
        severity="info",
        occurred_at=datetime.utcnow(),
        payload=payload,
    )

    session.add(event)
    session.commit()
    session.refresh(event)
    return event
