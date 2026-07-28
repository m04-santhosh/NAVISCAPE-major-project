"""
Prediction Pydantic Schemas
"""

from pydantic import BaseModel
from typing import Optional, List


class TrafficPredictionRequest(BaseModel):
    junction_id: int
    hours_ahead: int = 24


class TrafficPredictionResponse(BaseModel):
    junction_id: int
    predictions: List[dict]  # [{hour, predicted_count, congestion_level}, ...]


class RiskPredictionRequest(BaseModel):
    latitude: float
    longitude: float
    hour: Optional[int] = None
    weather: Optional[str] = "clear"


class RiskPredictionResponse(BaseModel):
    latitude: float
    longitude: float
    risk_score: float  # 0-100
    risk_level: str  # low, medium, high, critical
    factors: List[str] = []


class CongestionForecastResponse(BaseModel):
    junction_id: int
    junction_name: str
    forecasts: List[dict]  # [{hour, level, vehicle_count}, ...]
