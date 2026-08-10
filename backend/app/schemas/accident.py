"""
Accident Pydantic Schemas
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class AccidentRecordResponse(BaseModel):
    id: int
    district: Optional[str] = None
    police_station: Optional[str] = None
    crime_no: Optional[str] = None
    year: Optional[int] = None
    vehicles_involved: Optional[int] = None
    classification: Optional[str] = None
    main_cause: Optional[str] = None
    severity: Optional[str] = None
    accident_road: Optional[str] = None
    landmark_first: Optional[str] = None
    latitude: float
    longitude: float

    class Config:
        from_attributes = True


class HeatmapPoint(BaseModel):
    lat: float
    lng: float
    intensity: float
    severity_weight: float
    district: Optional[str] = None
    severity: Optional[str] = None


class AccidentCluster(BaseModel):
    cluster_id: int
    center_lat: float
    center_lng: float
    point_count: int
    district: str
    severity_summary: dict
    top_causes: List[str]
    sample_points: List[dict]


class AccidentStatsResponse(BaseModel):
    total_records: int
    records_with_coordinates: int
    districts_count: int
    top_districts: List[dict]
    severity_breakdown: dict
    yearly_trend: List[dict]
    top_causes: List[dict]
