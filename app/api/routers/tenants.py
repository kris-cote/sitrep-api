# app/api/routers/tenants.py
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select, Session
from uuid import UUID

from app.models.db import get_session
from app.models.entities import Tenant
from app.models.schemas import TenantCreate, TenantRead
from app.core.security import verify_api_key

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    tenant = Tenant(name=payload.name, plan_id=payload.plan_id)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant


@router.get("", response_model=List[TenantRead])
def list_tenants(
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    tenants = session.exec(select(Tenant)).all()
    return tenants


@router.get("/{tenant_id}", response_model=TenantRead)
def get_tenant(
    tenant_id: UUID,
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant
