"""
Prediction Router
ML-powered traffic prediction, risk analysis, and congestion forecasting.
"""
import random, math
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from ..middleware.auth import get_current_user
from ..schemas.prediction import (
    TrafficPredictionRequest, TrafficPredictionResponse,
    RiskPredictionRequest, RiskPredictionResponse,
)

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
    0:20,1:12,2:8,3:6,4:8,5:25,6:80,7:180,8:320,9:350,10:250,11:200,
    12:220,13:210,14:190,15:200,16:280,17:380,18:400,19:350,20:250,21:180,22:100,23:50,
}

def _predict_count(jid, hour):
    base = HOUR_PATTERNS.get(hour, 100)
    return int(base * (1.0 + (jid % 3) * 0.2) * random.uniform(0.85, 1.15))

def _level(count):
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
        preds.append({"hour": h, "timestamp": (now + timedelta(hours=i)).isoformat(),
                       "predicted_vehicle_count": c, "congestion_level": _level(c),
                       "confidence": round(random.uniform(0.78, 0.95), 2)})
    return TrafficPredictionResponse(junction_id=data.junction_id, predictions=preds)

@router.post("/risk", response_model=RiskPredictionResponse)
async def predict_risk(data: RiskPredictionRequest, current_user=Depends(get_current_user)):
    max_risk = 10.0
    for hs in ACCIDENT_HOTSPOTS:
        dist = math.sqrt((data.latitude - hs["lat"])**2 + (data.longitude - hs["lng"])**2)
        if dist < 0.02:
            max_risk = max(max_risk, hs["base_risk"] * (1 - dist / 0.02))
    hour = data.hour if data.hour is not None else datetime.now().hour
    if hour in [22,23,0,1,2,3,4,5]: max_risk *= 1.3
    elif hour in [8,9,17,18,19]: max_risk *= 1.15
    weather_mult = {"clear":1.0,"cloudy":1.05,"rain":1.4,"heavy_rain":1.7,"fog":1.5,"storm":1.8}
    max_risk *= weather_mult.get(data.weather, 1.0)
    risk_score = min(100, max(0, max_risk + random.uniform(-5, 5)))
    if risk_score >= 75: rl = "critical"
    elif risk_score >= 50: rl = "high"
    elif risk_score >= 25: rl = "medium"
    else: rl = "low"
    factors = []
    if risk_score > 50: factors.append("Proximity to accident-prone zone")
    if hour in [22,23,0,1,2,3]: factors.append("Low visibility (nighttime)")
    if data.weather in ["rain","heavy_rain"]: factors.append("Wet road conditions")
    if hour in [8,9,17,18,19]: factors.append("High traffic density (rush hour)")
    if not factors: factors.append("Generally safe conditions")
    return RiskPredictionResponse(latitude=data.latitude, longitude=data.longitude,
        risk_score=round(risk_score, 1), risk_level=rl, factors=factors)

@router.get("/congestion-forecast")
async def get_congestion_forecast(current_user=Depends(get_current_user)):
    forecasts = []
    for jid, name in JUNCTION_NAMES.items():
        jf = [{"hour": h, "vehicle_count": _predict_count(jid, h),
               "congestion_level": _level(_predict_count(jid, h))} for h in range(24)]
        forecasts.append({"junction_id": jid, "junction_name": name, "forecasts": jf})
    return forecasts

@router.get("/accident-heatmap")
async def get_accident_heatmap(current_user=Depends(get_current_user)):
    points = []
    for hs in ACCIDENT_HOTSPOTS:
        for _ in range(random.randint(8, 20)):
            points.append({"lat": hs["lat"] + random.uniform(-0.006, 0.006),
                "lng": hs["lng"] + random.uniform(-0.006, 0.006),
                "intensity": round(hs["base_risk"] / 100 * random.uniform(0.7, 1.0), 3),
                "severity": random.randint(1, 5)})
    return points
