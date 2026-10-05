"""
Pydantic Schemas for Women Safety — Emergency Events & SOS Trigger (WS-1)
"""

import math
from datetime import datetime
from typing import Optional, Union
from pydantic import BaseModel, ConfigDict, field_validator


class EmergencyTriggerRequest(BaseModel):
    """
    Request schema for triggering an emergency event.
    Accepts latitude, longitude, and optional accuracy_m.
    User identity is derived strictly from JWT authentication; user_id is never accepted.
    """
    latitude: float
    longitude: float
    accuracy_m: Optional[float] = None

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

    @field_validator("accuracy_m")
    @classmethod
    def validate_accuracy(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Accuracy must be a valid finite number.")
        if v < 0:
            raise ValueError("Accuracy cannot be negative.")
        return round(float(v), 2)


class EmergencyTriggerResponse(BaseModel):
    """
    Response schema returned upon creating an emergency event.
    Contains:
    - id
    - emergency_id
    - latitude
    - longitude
    - accuracy_m
    - triggered_at
    - status
    - success
    """
    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    emergency_id: Union[int, str]
    id: int
    latitude: float
    longitude: float
    accuracy_m: Optional[float] = None
    triggered_at: datetime
    status: str
