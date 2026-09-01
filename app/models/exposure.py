from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExposureAsset(SQLModel, table=True):
    __tablename__ = "exposure_assets"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    asset_type: str = Field(index=True)
    name: str = Field(index=True)
    latitude: float = Field(index=True)
    longitude: float = Field(index=True)
    population: Optional[int] = None
    criticality_score: float = 0.5
    vulnerability_score: float = 0.5
    source_system: str = "manual"
    source_id: Optional[str] = Field(default=None, index=True)
    properties: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
