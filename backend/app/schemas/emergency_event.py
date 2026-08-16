"""
Pydantic Schemas for Women Safety — Emergency Events & SOS Trigger
"""

import math
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


class EmergencyEventCreate(BaseModel):
    latitude: float
    longitude: float
    location_accuracy_m: Optional[float] = None

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if v is None or math.isnan(v) or math.isinf(v):
            raise ValueError("Latitude must be a valid finite number.")
        if not (-90.0 <= v <= 90.0):
            raise ValueError("Latitude must be between -90.0 and 90.0 degrees.")
        return round(float(v), 7)

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if v is None or math.isnan(v) or math.isinf(v):
            raise ValueError("Longitude must be a valid finite number.")
        if not (-180.0 <= v <= 180.0):
            raise ValueError("Longitude must be between -180.0 and 180.0 degrees.")
        return round(float(v), 7)

    @field_validator("location_accuracy_m")
    @classmethod
    def validate_accuracy(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Location accuracy must be a valid finite number.")
        if v < 0:
            raise ValueError("Location accuracy cannot be negative.")
        return round(float(v), 2)


class EmergencyEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    triggered_at: datetime
    cancelled_at: Optional[datetime] = None
    latitude: float
    longitude: float
    location_accuracy_m: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ActiveEmergencyResponse(BaseModel):
    has_active_event: bool
    event: Optional[EmergencyEventResponse] = None
