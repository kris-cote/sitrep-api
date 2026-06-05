from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class ObservationCreate(BaseModel):
    source_system: str
    source_type: str

    object_type: Optional[str] = None

    collected_at: datetime

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None

    confidence: Optional[float] = Field(default=0.5, ge=0, le=1)

    features: Optional[Dict[str, Any]] = {}
    raw_payload: Optional[Dict[str, Any]] = {}

    classification_tag: Optional[str] = "UNCLASSIFIED"
    tenant_id: Optional[str] = "default"
