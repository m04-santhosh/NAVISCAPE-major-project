"""
Prediction Router
Genuinely trained XGBoost accident risk prediction and historical accident intelligence.
"""
import math
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.accident import AccidentData
from ..schemas.prediction import (
    TrafficPredictionRequest, TrafficPredictionResponse,
    RiskPredictionRequest, RiskPredictionResponse,
)
from ..services.risk_ml import predict_xgboost_risk

router = APIRouter(prefix="/api/predict", tags=["Predictions"])

ACCIDENT_HOTSPOTS = [
    {"lat": 12.9170, "lng": 77.6230, "name": "Silk Board", "base_risk": 75},
    {"lat": 12.9340, "lng": 77.6100, "name": "BTM Layout", "base_risk": 60},
    {"lat": 13.0012, "lng": 77.6960, "name": "KR Puram", "base_risk": 65},
    {"lat": 12.9698, "lng": 77.7500, "name": "Whitefield", "base_risk": 55},
    {"lat": 12.9756, "lng": 77.6066, "name": "MG Road", "base_risk": 50},
    {"lat": 13.0358, "lng": 77.5970, "name": "Hebbal", "base_risk": 70},
    {"lat": 12.9591, "lng": 77.7010, "name": "Marathahalli", "base_risk": 68},
]

JUNCTION_NAMES = {
    1: "Silk Board Junction", 2: "Hebbal Flyover", 3: "KR Puram Junction",
    4: "Marathahalli Bridge", 5: "Whitefield Junction", 6: "Banashankari Circle",
    7: "Jayanagar 4th Block", 8: "MG Road Metro",
}

HOUR_PATTERNS = {
    0:20, 1:12, 2:8, 3:6, 4:8, 5:25, 6:80, 7:180, 8:320, 9:350, 10:250, 11:200,
    12:220, 13:210, 14:190, 15:200, 16:280, 17:380, 18:400, 19:350, 20:250, 21:180, 22:100, 23:50,
}

def _predict_count(jid: int, hour: int) -> int:
    base = HOUR_PATTERNS.get(hour, 100)
    return int(base * (1.0 + (jid % 3) * 0.2))

def _level(count: int) -> str:
    if count > 350: return "critical"
    if count > 250: return "high"
    if count > 150: return "medium"
    return "low"

@router.post("/traffic", response_model=TrafficPredictionResponse)
async def predict_traffic(data: TrafficPredictionRequest, current_user=Depends(get_current_user)):
    now = datetime.now()
    preds = []
    for i in range(data.hours_ahead):
        h = (now.hour + i) % 24
        c = _predict_count(data.junction_id, h)
        preds.append({
            "hour": h,
            "timestamp": (now + timedelta(hours=i)).isoformat(),
            "predicted_vehicle_count": c,
            "congestion_level": _level(c),
            "confidence": 0.85,
            "prediction_source": "hour_pattern_baseline",
        })
    return TrafficPredictionResponse(junction_id=data.junction_id, predictions=preds)

@router.post("/risk", response_model=RiskPredictionResponse)
async def predict_risk(
    data: RiskPredictionRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # ── 1. Real XGBoost Model Inference ──────────────────────────────────────
    weather_val = (data.weather or "Clear").capitalize()
    xgb_result = predict_xgboost_risk(
        latitude=data.latitude,
        longitude=data.longitude,
        weather=weather_val,
    )

    # ── 2. Empirical Database Historical Accident Density ─────────────────────
    db_accidents = (
        db.query(AccidentData.severity)
        .filter(
            AccidentData.latitude.between(data.latitude - 0.02, data.latitude + 0.02),
            AccidentData.longitude.between(data.longitude - 0.02, data.longitude + 0.02),
        )
        .limit(500)
        .all()
    )

    db_risk_boost = 0.0
    if db_accidents:
        cnt = len(db_accidents)
        fatals = sum(1 for a in db_accidents if a.severity == "Fatal")
        db_risk_boost = min(40.0, cnt * 0.6 + fatals * 2.0)

    # Proximity to major known hotspots
    hotspot_risk = 10.0
    for hs in ACCIDENT_HOTSPOTS:
        dist = math.sqrt((data.latitude - hs["lat"])**2 + (data.longitude - hs["lng"])**2)
        if dist < 0.02:
            hotspot_risk = max(hotspot_risk, hs["base_risk"] * (1 - dist / 0.02))

    # Blend XGBoost ML Prediction with DB Density & Hotspot Proximity
    if xgb_result.get("model_loaded") and xgb_result.get("predicted_risk_score") is not None:
        xgb_score = float(xgb_result["predicted_risk_score"])
        combined_risk = (xgb_score * 0.55) + (db_risk_boost * 0.30) + (hotspot_risk * 0.15)
    else:
        combined_risk = max(hotspot_risk, 10.0 + db_risk_boost)

    # Contextual multipliers (deterministic, zero random noise)
    hour = data.hour if data.hour is not None else datetime.now().hour
    if hour in [22, 23, 0, 1, 2, 3, 4, 5]:
        combined_risk *= 1.25
    elif hour in [8, 9, 17, 18, 19]:
        combined_risk *= 1.10

    weather_key = (data.weather or "clear").lower()
    weather_mult = {"clear": 1.0, "cloudy": 1.05, "rain": 1.35, "heavy_rain": 1.6, "fog": 1.45, "storm": 1.7}
    combined_risk *= weather_mult.get(weather_key, 1.0)

    risk_score = round(min(100.0, max(0.0, combined_risk)), 1)

    if risk_score >= 75: rl = "critical"
    elif risk_score >= 50: rl = "high"
    elif risk_score >= 25: rl = "medium"
    else: rl = "low"

    factors = []
    if xgb_result.get("model_loaded") and xgb_result.get("predicted_severity"):
        factors.append(f"XGBoost Classifier predicted severity: {xgb_result['predicted_severity']}")
    if db_accidents and len(db_accidents) >= 5:
        factors.append(f"High historical accident density ({len(db_accidents)} recorded incidents nearby)")
    elif risk_score > 50:
        factors.append("Proximity to accident-prone zone")
    if hour in [22, 23, 0, 1, 2, 3]: factors.append("Low visibility (nighttime)")
    if weather_key in ["rain", "heavy_rain"]: factors.append("Wet road conditions")
    if hour in [8, 9, 17, 18, 19]: factors.append("High traffic density (rush hour)")
    if not factors: factors.append("Generally safe conditions")

    return RiskPredictionResponse(
        latitude=data.latitude,
        longitude=data.longitude,
        risk_score=risk_score,
        risk_level=rl,
        factors=factors,
    )

@router.get("/congestion-forecast")
async def get_congestion_forecast(current_user=Depends(get_current_user)):
    forecasts = []
    for jid, name in JUNCTION_NAMES.items():
        jf = [
            {
                "hour": h,
                "vehicle_count": _predict_count(jid, h),
                "congestion_level": _level(_predict_count(jid, h)),
            }
            for h in range(24)
        ]
        forecasts.append({"junction_id": jid, "junction_name": name, "forecasts": jf})
    return forecasts

@router.get("/accident-heatmap")
async def get_accident_heatmap(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns genuine historical accident points from SQLite database for heatmap rendering."""
    records = (
        db.query(AccidentData.latitude, AccidentData.longitude, AccidentData.severity)
        .filter(AccidentData.latitude.isnot(None), AccidentData.longitude.isnot(None))
        .limit(500)
        .all()
    )
    sev_weights = {"Fatal": 1.0, "Grievous Injury": 0.8, "Simple Injury": 0.5, "Damage Only": 0.3}
    points = []
    for r in records:
        points.append({
            "lat": r.latitude,
            "lng": r.longitude,
            "intensity": round(sev_weights.get(r.severity, 0.5), 2),
            "severity": r.severity or "Unknown",
        })
    return points

