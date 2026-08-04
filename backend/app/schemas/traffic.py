"""
Traffic & Route Pydantic Schemas
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TrafficDataResponse(BaseModel):
    id: int
    junction_id: int
    latitude: float
    longitude: float
    timestamp: Optional[datetime] = None
    vehicle_count: int
    avg_speed: Optional[float] = None
    congestion_level: Optional[str] = None

    class Config:
        from_attributes = True


class HeatmapPoint(BaseModel):
    lat: float
    lng: float
    intensity: float


class RouteRequest(BaseModel):
    source_lat: float
    source_lng: float
    dest_lat: float
    dest_lng: float
    source_name: Optional[str] = None
    dest_name: Optional[str] = None
    route_type: str = "balanced"  # shortest, safest, balanced
    distance_km: Optional[float] = None
    duration_min: Optional[float] = None
    safety_score: Optional[float] = None


class RouteResponse(BaseModel):
    route_type: str
    distance_km: float
    duration_min: float
    safety_score: float
    waypoints: List[List[float]]  # [[lat, lng], ...]
    risk_zones: List[dict] = []
    congestion_segments: List[dict] = []


class RouteHistoryResponse(BaseModel):
    id: int
    source_name: Optional[str] = None
    dest_name: Optional[str] = None
    distance_km: Optional[float] = None
    duration_min: Optional[float] = None
    safety_score: Optional[float] = None
    route_type: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
