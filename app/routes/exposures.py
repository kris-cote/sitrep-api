from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.exposure import ExposureAsset


router = APIRouter(prefix="/exposures", tags=["exposures"])


class ExposureAssetCreate(BaseModel):
    tenant_id: str = "default"
    asset_type: str
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    population: Optional[int] = Field(default=None, ge=0)
    criticality_score: float = Field(default=0.5, ge=0, le=1)
    vulnerability_score: float = Field(default=0.5, ge=0, le=1)
    source_system: str = "manual"
    source_id: Optional[str] = None
    properties: Dict[str, Any] = {}


@router.post("", status_code=201)
def create_exposure_asset(payload: ExposureAssetCreate, session: Session = Depends(get_session)):
    if payload.source_id:
        existing = session.exec(
            select(ExposureAsset)
            .where(ExposureAsset.tenant_id == payload.tenant_id)
            .where(ExposureAsset.source_system == payload.source_system)
            .where(ExposureAsset.source_id == payload.source_id)
        ).first()
        if existing:
            return existing

    asset = ExposureAsset(**payload.model_dump())
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


@router.get("")
def list_exposure_assets(
    tenant_id: str = Query(default="default"),
    asset_type: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    statement = select(ExposureAsset).where(ExposureAsset.tenant_id == tenant_id)
    if asset_type:
        statement = statement.where(ExposureAsset.asset_type == asset_type)
    statement = statement.order_by(ExposureAsset.name).limit(limit)
    return list(session.exec(statement).all())


@router.get("/{asset_id}")
def get_exposure_asset(asset_id: str, session: Session = Depends(get_session)):
    asset = session.get(ExposureAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Exposure asset not found")
    return asset
