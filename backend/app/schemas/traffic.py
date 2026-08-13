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


class RouteEvaluationRequest(BaseModel):
    route_type: str = "balanced"
    waypoints: List[List[float]] = []


class RouteEvaluationResponse(BaseModel):
    route_type: str
    empirical_safety_score: float
    total_accidents_nearby: int
    fatal_accidents_nearby: int
    hotspots: List[dict] = []
    active_hazards_nearby: Optional[int] = 0
    live_hazards: Optional[List[dict]] = []


class CandidateRouteInput(BaseModel):
    route_id: Optional[str] = None
    route_type: Optional[str] = "balanced"
    distance_km: float = 0.0
    duration_min: float = 0.0
    waypoints: List[List[float]] = []


class OptimizeRoutesRequest(BaseModel):
    routes: List[CandidateRouteInput] = []


class EvaluatedRouteOutput(BaseModel):
    route_id: str
    route_type: str
    distance_km: float
    duration_min: float
    traffic_delay_minutes: float = 0.0
    hazard_delay_minutes: float = 0.0
    expected_delay_minutes: Optional[float] = 0.0
    eta_minutes: float
    safety_score: float
    accident_risk_score: float
    # Phase 4 traffic
    traffic_score: float
    predicted_traffic_score: Optional[float] = None
    eta_score: float
    distance_score: float
    overall_score: float
    risk_level: str
    traffic_level: str
    total_accidents_nearby: int
    fatal_accidents_nearby: int
    hotspots: List[dict] = []
    waypoints: List[List[float]] = []
    reasons: List[str] = []
    active_hazards_nearby: Optional[int] = 0
    live_hazards: Optional[List[dict]] = []
    # Phase 5 traffic intelligence fields
    current_traffic_score: Optional[float] = None
    predicted_congestion: Optional[str] = None
    traffic_source: Optional[str] = None
    traffic_confidence: Optional[float] = None
    prediction_available: bool = False
    prediction_horizon_minutes: int = 30


class OptimizeRoutesResponse(BaseModel):
    routes: List[EvaluatedRouteOutput]
    recommended_route_id: str
    recommendation_reasons: List[str]


# Phase 5: Dedicated route traffic evaluation endpoint schemas
class RouteTrafficRequest(BaseModel):
    waypoints: List[List[float]] = []
    distance_km: float = 0.0
    duration_min: float = 0.0
    prediction_horizon_minutes: int = 30


class RouteTrafficResponse(BaseModel):
    traffic_score: float
    current_traffic_score: float
    predicted_traffic_score: Optional[float] = None
    traffic_level: str
    predicted_congestion: Optional[str] = None
    expected_delay_minutes: Optional[float] = None
    traffic_source: str
    traffic_confidence: float
    prediction_available: bool
    prediction_horizon_minutes: int
