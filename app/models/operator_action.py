from typing import Optional
from pydantic import BaseModel, Field


class OperatorActionCreate(BaseModel):
    action_type: str = Field(
        ...,
        description="confirm, reject, flag, rename, adjust_confidence, note"
    )

    action_note: Optional[str] = None

    operator_id: Optional[str] = "operator"

    identity_label: Optional[str] = None

    adjusted_confidence: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Optional confidence override from operator review"
    )
