from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InfrastructureFeature(SQLModel, table=True):
    """Public/authorized infrastructure geometry used for continuity and exposure analysis.

    Geometry is stored as GeoJSON so points, lines and polygons can share one registry.
    This table is for planning/exposure context; sensitive operational attributes should
    not be copied into SitRep unless the deployment is explicitly authorized to hold them.
    """

    __tablename__ = "infrastructure_features"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    category: str = Field(index=True)  # transport, electric, telecom, water, fuel, emergency
    subtype: str = Field(default="general", index=True)
    name: str = Field(default="Unnamed feature", index=True)
    geometry_type: str = Field(default="Unknown", index=True)
    geometry: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    centroid_latitude: Optional[float] = Field(default=None, index=True)
    centroid_longitude: Optional[float] = Field(default=None, index=True)
    criticality_score: float = 0.5
    vulnerability_score: float = 0.5
    source_system: str = Field(default="manual", index=True)
    source_id: Optional[str] = Field(default=None, index=True)
    source_url: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
