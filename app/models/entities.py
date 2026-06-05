# app/models/entities.py
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON
from sqlmodel import SQLModel, Field, Relationship


class Tenant(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    name: str
    plan_id: str = "starter"
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    missions: list["Mission"] = Relationship(back_populates="tenant")
    devices: list["Device"] = Relationship(back_populates="tenant")


class Mission(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    tenant_id: UUID = Field(foreign_key="tenant.id")
    name: str
    mission_type: str  # e.g. "cubesat", "uav", "wildfire"
    status: str = "planned"  # planned, active, paused, completed, aborted
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    tenant: Tenant = Relationship(back_populates="missions")


class Event(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    tenant_id: Optional[UUID] = Field(default=None, foreign_key="tenant.id")
    mission_id: Optional[UUID] = Field(default=None, foreign_key="mission.id")
    event_type: str
    source_system: str
    severity: str = "info"
    occurred_at: datetime
    payload: Dict[str, Any] = Field(
    default_factory=dict,
    sa_column=Column(JSON),
)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Command(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    tenant_id: Optional[UUID] = Field(default=None, foreign_key="tenant.id")
    mission_id: Optional[UUID] = Field(default=None, foreign_key="mission.id")
    target: str  # device id or logical resource
    action: str
    params: Dict[str, Any] = Field(
    default_factory=dict,
    sa_column=Column(JSON),
)
    status: str = "queued"  # queued, sent, ack, failed
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Device(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    tenant_id: UUID = Field(foreign_key="tenant.id")
    name: str
    device_type: str  # e.g. "drone", "sensor-node", "host"
    status: str = "online"  # online, offline, degraded
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON),
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    tenant: Tenant = Relationship(back_populates="devices")


class Agent(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    name: str
    description: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
