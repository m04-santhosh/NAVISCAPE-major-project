"""
Road Hazard Pydantic Schemas
Validates hazard reporting requests and responses.
"""

from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

VALID_HAZARDS = {
    "Accident",
    "Pothole",
    "Road construction",
    "Road blocked",
    "Waterlogging",
    "Fallen tree",
    "Heavy traffic",
    "Dangerous road",
    "Other",
}

VALID_SEVERITIES = {"Low", "Medium", "High", "Critical"}


class HazardReportCreate(BaseModel):
    hazard_type: str
    severity: str
    latitude: float
    longitude: float
    description: Optional[str] = None

    @field_validator("hazard_type")
    @classmethod
    def validate_hazard_type(cls, v: str) -> str:
        if v not in VALID_HAZARDS:
            raise ValueError(f"Invalid hazard type. Must be one of: {', '.join(sorted(VALID_HAZARDS))}")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        if v not in VALID_SEVERITIES:
            raise ValueError(f"Invalid severity. Must be one of: {', '.join(sorted(VALID_SEVERITIES))}")
        return v

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if not (-90.0 <= v <= 90.0):
            raise ValueError("Latitude must be between -90.0 and 90.0")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if not (-180.0 <= v <= 180.0):
            raise ValueError("Longitude must be between -180.0 and 180.0")
        return v


class HazardReportResponse(BaseModel):
    id: int
    hazard_type: str
    severity: str
    latitude: float
    longitude: float
    description: Optional[str] = None
    created_at: datetime
    status: str
    user_id: int

    class Config:
        from_attributes = True
