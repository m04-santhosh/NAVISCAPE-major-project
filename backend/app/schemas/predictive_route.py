"""
Predictive Route Risk Pydantic Schemas
Defines request and response validation contracts for the Predictive Route Risk Engine (Phase 3A & Phase 3B).
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class CandidateRouteInput(BaseModel):
    route_id: Optional[str] = Field(default=None, description="Identifier for candidate route")
    route_type: Optional[str] = Field(default="balanced", description="Route profile e.g. shortest, safest, balanced")
    distance_km: float = Field(default=0.0, ge=0.0, description="Route physical distance in kilometers")
    duration_min: float = Field(default=0.0, ge=0.0, description="Base route travel duration in minutes")
    waypoints: List[List[float]] = Field(default_factory=list, description="Ordered [[lat, lng], ...] coordinates")


class RouteRiskPredictionRequest(BaseModel):
    source_lat: float = Field(..., ge=-90.0, le=90.0, description="Source latitude (-90 to 90)")
    source_lng: float = Field(..., ge=-180.0, le=180.0, description="Source longitude (-180 to 180)")
    destination_lat: float = Field(..., ge=-90.0, le=90.0, description="Destination latitude (-90 to 90)")
    destination_lng: float = Field(..., ge=-180.0, le=180.0, description="Destination longitude (-180 to 180)")
    waypoints: Optional[List[List[float]]] = Field(
        default=None,
        description="Optional ordered list of [latitude, longitude] route waypoints"
    )
    distance_km: Optional[float] = Field(default=None, ge=0.0, description="Total physical route distance in km")
    duration_min: Optional[float] = Field(default=None, ge=0.0, description="Base route travel duration in minutes")
    weather: Optional[str] = Field(default="Clear", description="Weather condition (e.g., Clear, Rain, Fog)")
    road_condition: Optional[str] = Field(default="Not Applicable", description="Road condition context")
    surface_condition: Optional[str] = Field(default="Not Applicable", description="Surface condition context")

    @field_validator("waypoints")
    @classmethod
    def validate_waypoints(cls, v: Optional[List[List[float]]]) -> Optional[List[List[float]]]:
        if v is not None:
            for pt in v:
                if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                    raise ValueError("Each waypoint entry must be a [latitude, longitude] pair")
                lat, lng = float(pt[0]), float(pt[1])
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
                    raise ValueError(f"Waypoint coordinate out of valid range: [{lat}, {lng}]")
        return v


class AccidentExposure(BaseModel):
    level: str = Field(..., description="Historical accident exposure classification: LOW, MODERATE, or HIGH")
    nearby_accidents: int = Field(..., ge=0, description="Total historical accidents within proximity of route")
    severe_accidents: int = Field(..., ge=0, description="Count of fatal and grievous injury incidents nearby")


class TrafficRisk(BaseModel):
    level: str = Field(..., description="Traffic congestion risk level: LOW, MODERATE, HIGH, or UNKNOWN")
    traffic_score: Optional[float] = Field(default=None, description="0-100 traffic score (higher = less congestion)")
    traffic_source: Optional[str] = Field(default=None, description="Source of traffic intelligence data")
    expected_delay_minutes: Optional[float] = Field(default=None, description="Estimated delay in minutes")


class RiskHotspot(BaseModel):
    latitude: float
    longitude: float
    severity: str
    risk_score: float
    nearby_accidents: int
    description: str


class RouteRiskPredictionResponse(BaseModel):
    predicted_safety_score: float = Field(..., ge=0.0, le=100.0, description="Predicted safety score (0 to 100)")
    risk_level: str = Field(..., description="Risk category: LOW, MODERATE, or HIGH")
    accident_exposure: AccidentExposure
    traffic_risk: TrafficRisk
    risk_hotspots: List[RiskHotspot] = Field(default_factory=list)
    factors: List[str] = Field(default_factory=list, description="Descriptive deterministic explanation factors")
    model_used: str = Field(default="xgboost_severity_classifier", description="ML model identifier")


# ── Phase 3B: Predictive Route Comparison Schemas ────────────────────────────

class RouteComparisonItem(BaseModel):
    route_id: str
    route_type: str = "balanced"
    distance_km: float = 0.0
    duration_min: float = 0.0
    predicted_safety_score: float = 0.0
    risk_level: str = "LOW"
    accident_exposure: AccidentExposure
    traffic_risk: TrafficRisk
    risk_hotspots: List[RiskHotspot] = Field(default_factory=list)
    waypoints: List[List[float]] = Field(default_factory=list)
    factors: List[str] = Field(default_factory=list)


class RouteTradeOffSummary(BaseModel):
    distance_difference_km: Optional[float] = Field(default=None, description="Difference between max and min route distance")
    duration_difference_min: Optional[float] = Field(default=None, description="Difference between max and min route duration")
    safety_score_difference: Optional[float] = Field(default=None, description="Difference between max and min predicted safety score")
    accident_exposure_difference: Optional[int] = Field(default=None, description="Difference in nearby historical accident counts")
    traffic_score_difference: Optional[float] = Field(default=None, description="Difference in traffic scores if available")
    tradeoff_notes: List[str] = Field(default_factory=list, description="Objective factual differences between route options")


class RouteComparisonRequest(BaseModel):
    source_lat: float = Field(..., ge=-90.0, le=90.0, description="Source latitude (-90 to 90)")
    source_lng: float = Field(..., ge=-180.0, le=180.0, description="Source longitude (-180 to 180)")
    destination_lat: float = Field(..., ge=-90.0, le=90.0, description="Destination latitude (-90 to 90)")
    destination_lng: float = Field(..., ge=-180.0, le=180.0, description="Destination longitude (-180 to 180)")
    routes: Optional[List[CandidateRouteInput]] = Field(
        default=None,
        description="Optional list of candidate route options; if omitted, alternatives will be fetched from OSRM"
    )
    weather: Optional[str] = Field(default="Clear", description="Weather context")
    road_condition: Optional[str] = Field(default="Not Applicable", description="Road condition context")
    surface_condition: Optional[str] = Field(default="Not Applicable", description="Surface condition context")


class RouteComparisonResponse(BaseModel):
    routes: List[RouteComparisonItem] = Field(default_factory=list)
    trade_off_summary: Optional[RouteTradeOffSummary] = Field(default=None)
    alternatives_available: bool = Field(..., description="True if 2 or more real route alternatives were compared")
    model_used: str = Field(default="xgboost_severity_classifier")
