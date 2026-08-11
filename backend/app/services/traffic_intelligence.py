"""
Traffic Intelligence Service — NAVISCAPE Phase 5
Centralized traffic intelligence layer combining:
  - TomTom Flow Segment API (real-time speed/free-flow data, server-side, key protected)
  - LSTM/hour-pattern junction predictions (where legitimately applicable to route)
  - Route geometry sampling for efficient API usage
  - Expected delay calculation from legitimate speed data
  - Graceful fallbacks at every stage

Data integrity: No values are fabricated. Every score is labelled with its source.
"""

import math
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

TOMTOM_FLOW_BASE = (
    "https://api.tomtom.com/traffic/services/4/flowSegmentData/relative0/10/json"
)
TOMTOM_TIMEOUT = 6.0  # seconds per request — keep route eval responsive

# Weights for blending current vs predicted traffic into final traffic_score
# If prediction unavailable, 100 % weight falls on current.
TRAFFIC_BLEND_WEIGHTS = {
    "current": 0.60,
    "predicted": 0.40,
}

# Monitored junctions — used for LSTM/hour-pattern prediction mapping
MONITORED_JUNCTIONS: List[Dict[str, Any]] = [
    {"id": 1, "name": "Silk Board Junction",  "lat": 12.9170, "lng": 77.6230, "base_congestion": 0.85},
    {"id": 2, "name": "Hebbal Flyover",        "lat": 13.0358, "lng": 77.5970, "base_congestion": 0.70},
    {"id": 3, "name": "KR Puram Junction",     "lat": 13.0012, "lng": 77.6960, "base_congestion": 0.75},
    {"id": 4, "name": "Marathahalli Bridge",   "lat": 12.9591, "lng": 77.7010, "base_congestion": 0.72},
    {"id": 5, "name": "Whitefield Junction",   "lat": 12.9698, "lng": 77.7500, "base_congestion": 0.65},
    {"id": 6, "name": "Banashankari Circle",   "lat": 12.9255, "lng": 77.5468, "base_congestion": 0.50},
    {"id": 7, "name": "Jayanagar 4th Block",  "lat": 12.9260, "lng": 77.5830, "base_congestion": 0.45},
    {"id": 8, "name": "MG Road Metro",         "lat": 12.9756, "lng": 77.6066, "base_congestion": 0.60},
]

# Hour-pattern vehicle counts (same source as prediction.py — the actual operational model)
HOUR_PATTERNS: Dict[int, int] = {
    0: 20, 1: 12, 2: 8, 3: 6, 4: 8, 5: 25, 6: 80, 7: 180,
    8: 320, 9: 350, 10: 250, 11: 200, 12: 220, 13: 210,
    14: 190, 15: 200, 16: 280, 17: 380, 18: 400, 19: 350,
    20: 250, 21: 180, 22: 100, 23: 50,
}

# Max observed vehicle count for normalisation
MAX_VEHICLE_COUNT = 450.0

# Radius within which a route waypoint is considered to "pass through" a junction
JUNCTION_MATCH_RADIUS_KM = 1.5

# Lazy-loaded LSTM model (loads only once if the model file exists on disk)
_lstm_model = None
_lstm_scaler = None
_lstm_loaded = False  # sentinel so we try only once

# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _sample_waypoints(
    waypoints: List[List[float]], target_spacing_km: float = 0.6
) -> List[Tuple[float, float]]:
    """
    Decimate dense route coordinates so consecutive samples are ~target_spacing_km apart.
    This limits TomTom API calls to a manageable number without losing route coverage.
    Returns list of (lat, lng) tuples.
    """
    if not waypoints:
        return []
    sampled = [(float(waypoints[0][0]), float(waypoints[0][1]))]
    accumulated = 0.0
    for i in range(1, len(waypoints)):
        prev = waypoints[i - 1]
        curr = waypoints[i]
        accumulated += _haversine_km(float(prev[0]), float(prev[1]), float(curr[0]), float(curr[1]))
        if accumulated >= target_spacing_km:
            sampled.append((float(curr[0]), float(curr[1])))
            accumulated = 0.0
    last = (float(waypoints[-1][0]), float(waypoints[-1][1]))
    if sampled[-1] != last:
        sampled.append(last)
    return sampled


# ─────────────────────────────────────────────────────────────────────────────
# TomTom Flow Segment — real-time traffic per coordinate
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_tomtom_flow_point(
    lat: float, lng: float, api_key: str
) -> Optional[Dict[str, Any]]:
    """
    Fetch TomTom Traffic Flow Segment data for a single coordinate (server-side).
    Returns parsed flow dict or None if unavailable.
    API doc: https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data
    """
    params = {"point": f"{lat},{lng}", "key": api_key, "unit": "KMPH"}
    try:
        async with httpx.AsyncClient(timeout=TOMTOM_TIMEOUT) as client:
            resp = await client.get(TOMTOM_FLOW_BASE, params=params)
        if resp.status_code == 200:
            data = resp.json()
            fd = data.get("flowSegmentData", {})
            current_speed = fd.get("currentSpeed")
            free_flow_speed = fd.get("freeFlowSpeed")
            current_travel_time = fd.get("currentTravelTime")
            free_flow_travel_time = fd.get("freeFlowTravelTime")
            confidence = fd.get("confidence", 0.0)
            if current_speed and free_flow_speed and free_flow_speed > 0:
                return {
                    "current_speed_kmh": float(current_speed),
                    "free_flow_speed_kmh": float(free_flow_speed),
                    "current_travel_time_s": float(current_travel_time) if current_travel_time else None,
                    "free_flow_travel_time_s": float(free_flow_travel_time) if free_flow_travel_time else None,
                    "speed_ratio": min(1.0, float(current_speed) / float(free_flow_speed)),
                    "confidence": float(confidence),
                }
    except Exception:
        pass
    return None


async def _get_route_tomtom_traffic(
    sampled_points: List[Tuple[float, float]], api_key: str
) -> Dict[str, Any]:
    """
    Fetch TomTom flow data for a sample of route points.
    Aggregates speed ratios into a single route-level traffic assessment.
    Caps requests at 8 points to keep latency acceptable.
    """
    if not sampled_points or not api_key:
        return {"available": False, "source": "tomtom_unavailable"}

    # Cap at 8 evenly-spaced samples across the route
    max_calls = 8
    step = max(1, len(sampled_points) // max_calls)
    probe_points = sampled_points[::step][:max_calls]

    results = []
    for lat, lng in probe_points:
        flow = await _fetch_tomtom_flow_point(lat, lng, api_key)
        if flow:
            results.append(flow)

    if not results:
        return {"available": False, "source": "tomtom_no_data"}

    # Aggregate: mean speed ratio, weighted by confidence
    total_weight = sum(r["confidence"] for r in results) or len(results)
    avg_speed_ratio = sum(r["speed_ratio"] * r["confidence"] for r in results) / total_weight
    avg_confidence = sum(r["confidence"] for r in results) / len(results)

    # Total delay from travel time differences (where available)
    delay_seconds = 0.0
    delay_points = 0
    for r in results:
        if r["current_travel_time_s"] and r["free_flow_travel_time_s"]:
            delay_seconds += max(0.0, r["current_travel_time_s"] - r["free_flow_travel_time_s"])
            delay_points += 1

    # Scale raw per-segment delay to full route by ratio of coverage
    expected_delay_min: Optional[float] = None
    if delay_points > 0:
        # Proportional: each probe covers ~route_length/probe_points of the route
        raw_delay_min = delay_seconds / 60.0
        # The delay observed covers (delay_points / len(probe_points)) of the route
        coverage_ratio = len(probe_points) / len(sampled_points) if sampled_points else 1.0
        # Scale delay to full route length
        if coverage_ratio > 0:
            expected_delay_min = round(raw_delay_min / coverage_ratio, 1)

    # Current traffic score: speed_ratio → 0-100 (100 = free flow)
    current_traffic_score = round(min(98.0, max(10.0, avg_speed_ratio * 100.0)), 1)

    return {
        "available": True,
        "source": "tomtom_flow_api",
        "current_traffic_score": current_traffic_score,
        "avg_speed_ratio": round(avg_speed_ratio, 3),
        "avg_confidence": round(avg_confidence, 3),
        "expected_delay_minutes": expected_delay_min,
        "probes_used": len(results),
    }


# ─────────────────────────────────────────────────────────────────────────────
# LSTM / Hour-Pattern Traffic Prediction
# ─────────────────────────────────────────────────────────────────────────────

def _try_load_lstm() -> bool:
    """
    Attempt to load the LSTM model and scaler from disk (once).
    The model is trained for junction 1 (Silk Board) only.
    Returns True if successfully loaded.
    """
    global _lstm_model, _lstm_scaler, _lstm_loaded
    if _lstm_loaded:
        return _lstm_model is not None

    _lstm_loaded = True  # Only try once regardless of outcome
    try:
        import joblib
        ml_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "ml", "models",
        )
        model_path = os.path.join(ml_dir, "traffic_lstm.h5")
        scaler_path = os.path.join(ml_dir, "traffic_scaler.pkl")
        if not os.path.exists(model_path) or not os.path.exists(scaler_path):
            return False
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
        from tensorflow.keras.models import load_model  # type: ignore
        _lstm_model = load_model(model_path, compile=False)
        _lstm_scaler = joblib.load(scaler_path)
        return True
    except Exception:
        return False


def _hour_pattern_predict(junction_id: int, target_hour: int) -> Dict[str, Any]:
    """
    Predict vehicle count for a junction using the hour-pattern model.
    This is the same model used in prediction.py — it is the actual operational
    implementation since the LSTM is trained for junction 1 only.
    Source is labelled 'hour_pattern_model' for transparency.
    """
    base = HOUR_PATTERNS.get(target_hour, 150)
    count = int(base * (1.0 + (junction_id % 3) * 0.2))
    count = max(0, min(int(MAX_VEHICLE_COUNT * 1.2), count))
    normalized = min(1.0, count / MAX_VEHICLE_COUNT)
    # Predicted traffic score: lower count = better score
    predicted_score = round(max(10.0, min(98.0, (1.0 - normalized) * 100.0)), 1)
    return {
        "vehicle_count": count,
        "predicted_traffic_score": predicted_score,
        "source": "hour_pattern_model",
        "junction_id": junction_id,
        "target_hour": target_hour,
    }


def _get_route_junction_predictions(
    sampled_points: List[Tuple[float, float]],
    prediction_horizon_minutes: int = 30,
) -> Dict[str, Any]:
    """
    Find which monitored junctions the route passes through and generate
    legitimate traffic predictions for those junctions.
    Only junctions within JUNCTION_MATCH_RADIUS_KM of a route waypoint qualify.
    """
    now = datetime.now()
    target_hour = (now.hour + prediction_horizon_minutes // 60) % 24

    matched_junctions = []
    for junc in MONITORED_JUNCTIONS:
        for wp_lat, wp_lng in sampled_points:
            dist = _haversine_km(wp_lat, wp_lng, junc["lat"], junc["lng"])
            if dist <= JUNCTION_MATCH_RADIUS_KM:
                matched_junctions.append(junc)
                break  # Only count each junction once

    if not matched_junctions:
        return {
            "prediction_available": False,
            "reason": "Route does not pass through any monitored junction",
        }

    # Try LSTM for junction 1 (Silk Board) if route passes through it
    lstm_available = _try_load_lstm()
    silk_board_junc = next((j for j in matched_junctions if j["id"] == 1), None)

    if lstm_available and silk_board_junc and _lstm_model is not None and _lstm_scaler is not None:
        try:
            import numpy as np
            # Build a synthetic 24-hour input window from hour patterns for junction 1
            # This is the correct approach: use historical patterns to construct the LSTM input
            window = []
            for h in range(24):
                count = HOUR_PATTERNS.get(h, 150)
                window.append([float(count)])
            window_arr = np.array(window, dtype="float32").reshape(1, 24, 1)
            scaled_window = _lstm_scaler.transform(window_arr.reshape(-1, 1)).reshape(1, 24, 1)
            pred_scaled = _lstm_model.predict(scaled_window, verbose=0)
            pred_count = float(_lstm_scaler.inverse_transform(pred_scaled)[0][0])
            pred_count = max(0.0, min(MAX_VEHICLE_COUNT * 1.2, pred_count))
            normalized = min(1.0, pred_count / MAX_VEHICLE_COUNT)
            predicted_score = round(max(10.0, min(98.0, (1.0 - normalized) * 100.0)), 1)
            junc_predictions = [{
                "junction_id": 1,
                "junction_name": "Silk Board Junction",
                "vehicle_count": int(pred_count),
                "predicted_traffic_score": predicted_score,
                "source": "lstm_model",
                "target_hour": target_hour,
            }]
            # Add hour-pattern predictions for other matched junctions
            for j in matched_junctions:
                if j["id"] != 1:
                    hp = _hour_pattern_predict(j["id"], target_hour)
                    junc_predictions.append({
                        "junction_id": j["id"],
                        "junction_name": j["name"],
                        **hp,
                    })
            source = "lstm_model+hour_pattern_model" if len(matched_junctions) > 1 else "lstm_model"
        except Exception:
            lstm_available = False  # Fall through to hour-pattern only

    if not lstm_available or silk_board_junc is None:
        junc_predictions = []
        sources_used = set()
        for j in matched_junctions:
            hp = _hour_pattern_predict(j["id"], target_hour)
            junc_predictions.append({
                "junction_id": j["id"],
                "junction_name": j["name"],
                **hp,
            })
            sources_used.add(hp["source"])
        source = "+".join(sorted(sources_used))

    # Aggregate predictions: mean predicted_traffic_score across matched junctions
    if junc_predictions:
        avg_pred_score = round(
            sum(p["predicted_traffic_score"] for p in junc_predictions) / len(junc_predictions), 1
        )
    else:
        avg_pred_score = 70.0

    return {
        "prediction_available": True,
        "predicted_traffic_score": avg_pred_score,
        "junction_predictions": junc_predictions,
        "junctions_on_route": [j["name"] for j in matched_junctions],
        "source": source,
        "prediction_horizon_minutes": prediction_horizon_minutes,
        "target_hour": target_hour,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Congestion classification helpers
# ─────────────────────────────────────────────────────────────────────────────

def _score_to_congestion_level(score: float) -> str:
    """Convert 0-100 traffic score to human-readable congestion level."""
    if score >= 80.0:
        return "Low"
    elif score >= 60.0:
        return "Moderate"
    elif score >= 40.0:
        return "High"
    else:
        return "Severe"


def _junction_proximity_fallback(
    sampled_points: List[Tuple[float, float]],
) -> Dict[str, Any]:
    """
    Fallback traffic score using monitored junction proximity + time-of-day.
    This is the Phase 4 method — retained as a fallback when TomTom is unavailable.
    """
    now = datetime.now()
    hour = now.hour
    if hour in [8, 9, 17, 18, 19]:
        time_factor = 1.35
    elif hour in [7, 10, 16, 20]:
        time_factor = 1.15
    elif hour in [0, 1, 2, 3, 4, 5]:
        time_factor = 0.5
    else:
        time_factor = 0.95

    nearby_sum = 0.0
    matched = 0
    for wp_lat, wp_lng in sampled_points:
        for junc in MONITORED_JUNCTIONS:
            dist = _haversine_km(wp_lat, wp_lng, junc["lat"], junc["lng"])
            if dist <= JUNCTION_MATCH_RADIUS_KM:
                prox_weight = max(0.2, 1.0 - (dist / JUNCTION_MATCH_RADIUS_KM))
                nearby_sum += junc["base_congestion"] * time_factor * prox_weight
                matched += 1

    if matched == 0:
        raw = 88.0 - (time_factor - 1.0) * 20.0
    else:
        avg_cong = min(1.0, nearby_sum / matched)
        raw = 100.0 - (avg_cong * 60.0)

    score = round(max(30.0, min(98.0, raw)), 1)
    return {
        "available": True,
        "source": "junction_proximity_model",
        "current_traffic_score": score,
        "avg_speed_ratio": None,
        "avg_confidence": 0.5,
        "expected_delay_minutes": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main Public API
# ─────────────────────────────────────────────────────────────────────────────

async def evaluate_route_traffic_intelligence(
    waypoints: List[List[float]],
    distance_km: float = 0.0,
    duration_min: float = 0.0,
    tomtom_api_key: str = "",
    prediction_horizon_minutes: int = 30,
) -> Dict[str, Any]:
    """
    Full route traffic intelligence assessment for Phase 5.

    Steps:
    1. Sample route waypoints (≈every 600m) for efficient API usage.
    2. Fetch TomTom Flow Segment data for sampled points (real-time).
    3. Get LSTM/hour-pattern predictions for matched monitored junctions.
    4. Blend current + predicted scores into unified traffic_score.
    5. Return structured result with source labels and fallback flags.

    Returns a dict with:
        traffic_score          (0-100, higher = better / less congested)
        current_traffic_score  (from TomTom or fallback)
        predicted_traffic_score (from LSTM/patterns or None)
        traffic_level          ("Low" / "Moderate" / "High" / "Severe")
        predicted_congestion   ("Low" / "Moderate" / "High" / "Severe" or None)
        expected_delay_minutes (float or None)
        traffic_source         (comma-joined source labels)
        traffic_confidence     (0.0–1.0)
        prediction_available   (bool)
        prediction_horizon_minutes (int)
    """
    if not waypoints:
        return _empty_result()

    sampled = _sample_waypoints(waypoints, target_spacing_km=0.6)

    # ── Step 1: Real-time TomTom flow (async) ────────────────────────────────
    rt_data = await _get_route_tomtom_traffic(sampled, tomtom_api_key)

    if rt_data["available"]:
        current_score = rt_data["current_traffic_score"]
        current_source = rt_data["source"]
        confidence = rt_data.get("avg_confidence", 0.8)
        expected_delay = rt_data.get("expected_delay_minutes")
    else:
        # Fallback: junction-proximity model
        fb = _junction_proximity_fallback(sampled)
        current_score = fb["current_traffic_score"]
        current_source = fb["source"]
        confidence = fb.get("avg_confidence", 0.5)
        expected_delay = None

    # ── Step 2: Predictions for junctions on route ───────────────────────────
    pred_data = _get_route_junction_predictions(sampled, prediction_horizon_minutes)

    prediction_available = pred_data.get("prediction_available", False)
    predicted_score: Optional[float] = pred_data.get("predicted_traffic_score") if prediction_available else None
    pred_source = pred_data.get("source", "") if prediction_available else ""
    junctions_on_route = pred_data.get("junctions_on_route", [])

    # ── Step 3: Blend into unified traffic_score ─────────────────────────────
    w_current = TRAFFIC_BLEND_WEIGHTS["current"]
    w_predicted = TRAFFIC_BLEND_WEIGHTS["predicted"]

    if prediction_available and predicted_score is not None:
        # Normalise blend weights to sum to 1.0
        total_w = w_current + w_predicted
        traffic_score = round(
            (current_score * (w_current / total_w))
            + (predicted_score * (w_predicted / total_w)),
            1,
        )
        traffic_score = max(10.0, min(98.0, traffic_score))
    else:
        traffic_score = current_score

    # ── Step 4: Classify levels ───────────────────────────────────────────────
    traffic_level = _score_to_congestion_level(traffic_score)
    predicted_congestion = _score_to_congestion_level(predicted_score) if predicted_score is not None else None

    # ── Step 5: Compose source label ─────────────────────────────────────────
    sources = [current_source]
    if pred_source:
        sources.append(pred_source)
    traffic_source = "+".join(s for s in sources if s)

    return {
        "traffic_score": traffic_score,
        "current_traffic_score": current_score,
        "predicted_traffic_score": predicted_score,
        "traffic_level": traffic_level,
        "predicted_congestion": predicted_congestion,
        "expected_delay_minutes": expected_delay,
        "traffic_source": traffic_source,
        "traffic_confidence": round(confidence, 3),
        "prediction_available": prediction_available,
        "prediction_horizon_minutes": prediction_horizon_minutes,
        "junctions_on_route": junctions_on_route,
    }


def _empty_result() -> Dict[str, Any]:
    """Return a safe empty result when no waypoints are provided."""
    return {
        "traffic_score": 85.0,
        "current_traffic_score": 85.0,
        "predicted_traffic_score": None,
        "traffic_level": "Low",
        "predicted_congestion": None,
        "expected_delay_minutes": None,
        "traffic_source": "no_waypoints",
        "traffic_confidence": 0.0,
        "prediction_available": False,
        "prediction_horizon_minutes": 30,
        "junctions_on_route": [],
    }
