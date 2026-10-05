"""
Pydantic Schemas for Women Safety WS-3 Emergency Orchestration & Actions Audit Log
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, field_validator


class EmergencyActionCreate(BaseModel):
    action_type: str
    contact_type: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("action_type cannot be empty.")
        upper_v = v.strip().upper()
        valid_types = {
            "SOS_ACTIVATED",
            "GPS_CAPTURED",
            "EMERGENCY_REGISTERED",
            "WHATSAPP_PREPARED",
            "WHATSAPP_OPENED",
            "ALERT_SENT_CONFIRMED",
            "EMERGENCY_CANCELLED",
            "EMERGENCY_RESOLVED",
            "EMERGENCY_CONTACT_CALLED",
            "POLICE_CALLED",
        }
        if upper_v not in valid_types:
            return upper_v
        return upper_v


class EmergencyActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    emergency_event_id: int
    user_id: int
    action_type: str
    contact_type: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: datetime
    description: Optional[str] = None


class TimelineItemResponse(BaseModel):
    id: int
    action_type: str
    contact_type: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    created_at: datetime
    description: str


class EmergencyTimelineResponse(BaseModel):
    emergency_id: int
    status: str
    timeline: List[TimelineItemResponse]


class StatusUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("status cannot be empty.")
        upper_v = v.strip().upper()
        allowed = {"ACTIVE", "ALERTS_PREPARED", "CONTACTS_NOTIFIED", "CANCELLED", "RESOLVED"}
        if upper_v not in allowed:
            raise ValueError(f"Invalid status '{v}'. Allowed: {', '.join(sorted(allowed))}")
        return upper_v
