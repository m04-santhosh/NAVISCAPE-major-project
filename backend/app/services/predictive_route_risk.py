"""
Predictive Route Risk Service — NAVISCAPE Phase 3A
Combines XGBoost ML severity classification, historical Karnataka accident density,
live user-reported road hazards, and TomTom traffic intelligence into a unified
predictive route risk assessment.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from .risk_ml import _load_xgboost_model, predict_xgboost_risk
from .route_safety import (
    decimate_waypoints,
    evaluate_route_safety,
    haversine_distance,
)
from .traffic_intelligence import evaluate_route_traffic_intelligence
from ..config import settings

logger = logging.getLogger(__name__)

# Centralized Risk Classification Thresholds
# 80-100: LOW, 60-79: MODERATE, 0-59: HIGH
def score_to_risk_level(score: float) -> str:
    """Converts 0-100 safety score to standard risk level classification."""
    if score >= 80.0:
        return "LOW"
    elif score >= 60.0:
        return "MODERATE"
    else:
        return "HIGH"


def determine_accident_exposure(total_accidents: int, severe_accidents: int) -> str:
    """Calculates historical accident exposure category based on actual counts."""
    if total_accidents == 0:
        return "LOW"
    if total_accidents <= 10 and severe_accidents <= 2:
        return "LOW"
    if total_accidents <= 35 and severe_accidents <= 6:
        return "MODERATE"
    return "HIGH"


def determine_traffic_risk_level(traffic_score: Optional[float], traffic_source: Optional[str]) -> str:
    """Classifies traffic risk level, returning UNKNOWN if genuine data is unavailable."""
    if traffic_score is None or traffic_source in (None, "unavailable", "no_waypoints"):
        return "UNKNOWN"
    if traffic_score >= 80.0:
        return "LOW"
    elif traffic_score >= 60.0:
        return "MODERATE"
    else:
        return "HIGH"


def evaluate_predictive_route_risk(
    db: Session,
    source_lat: float,
    source_lng: float,
    destination_lat: float,
    destination_lng: float,
    waypoints: Optional[List[List[float]]] = None,
    distance_km: Optional[float] = None,
    duration_min: Optional[float] = None,
    weather: str = "Clear",
    road_condition: str = "Not Applicable",
    surface_condition: str = "Not Applicable",
) -> Dict[str, Any]:
    """
    Evaluates end-to-end predictive route risk.

    Data Integration Flow:
      1. Waypoint preparation & geometric decimation.
      2. Empirical accident density & severe accident analysis from SQLite.
      3. Live road hazard proximity & delay calculation.
      4. XGBoost ML severity classification inference along route waypoints.
      5. Traffic flow intelligence assessment (real-time + forecast).
      6. Synthesis into unified predicted safety score, risk level, and real hotspots.
    """
    # ── Step 1: Waypoint Resolution ──────────────────────────────────────────
    if not waypoints or len(waypoints) < 2:
        effective_waypoints = [
            [float(source_lat), float(source_lng)],
            [float(destination_lat), float(destination_lng)],
        ]
    else:
        effective_waypoints = [[float(pt[0]), float(pt[1])] for pt in waypoints]

    sampled_points = decimate_waypoints(effective_waypoints, target_spacing_km=0.4)
    if not sampled_points:
        sampled_points = [(float(source_lat), float(source_lng)), (float(destination_lat), float(destination_lng))]

    # ── Step 2: Historical Accident & Hazard Analysis ─────────────────────────
    safety_eval = evaluate_route_safety(db, waypoints=effective_waypoints, search_radius_km=0.3)
    total_accidents = int(safety_eval.get("total_accidents_nearby", 0))
    fatal_accidents = int(safety_eval.get("fatal_accidents_nearby", 0))
    hotspots_raw = safety_eval.get("hotspots", [])
    active_hazards = int(safety_eval.get("active_hazards_nearby", 0))

    # Calculate severe accidents count (Fatal + Grievous Injury)
    grievous_count = 0
    for h in hotspots_raw:
        sev_summary = h.get("severity_summary", {})
        grievous_count += sev_summary.get("Grievous Injury", 0)
    severe_accidents = fatal_accidents + grievous_count

    accident_exposure_level = determine_accident_exposure(total_accidents, severe_accidents)

    # ── Step 3: XGBoost Predictive Inference Along Route ─────────────────────
    ml_risk_scores: List[float] = []
    top_predicted_severities: Dict[str, int] = {}
    model_loaded = False
    model_name = "xgboost_unavailable"

    # Evaluate XGBoost model across sampled points along the route
    for lat, lng in sampled_points:
        pred_res = predict_xgboost_risk(
            latitude=lat,
            longitude=lng,
            weather=weather,
            road_condition=road_condition,
            surface_condition=surface_condition,
        )
        if pred_res.get("model_loaded"):
            model_loaded = True
            model_name = pred_res.get("model_name", "xgboost_severity_classifier")
            risk_score = pred_res.get("predicted_risk_score")
            if risk_score is not None:
                ml_risk_scores.append(float(risk_score))
            sev = pred_res.get("predicted_severity")
            if sev:
                top_predicted_severities[sev] = top_predicted_severities.get(sev, 0) + 1

    if ml_risk_scores:
        avg_ml_risk = sum(ml_risk_scores) / len(ml_risk_scores)
        # Convert ML risk score (0-100 high risk) to ML safety index (0-100 high safety)
        ml_safety_score = max(20.0, min(98.0, 100.0 - avg_ml_risk))
    else:
        avg_ml_risk = None
        ml_safety_score = None

    # ── Step 4: Empirical Safety & Blending ───────────────────────────────────
    empirical_score = float(safety_eval.get("empirical_safety_score", 85.0))

    if ml_safety_score is not None:
        # Blend: 40% XGBoost predictive inference + 60% Empirical historical & live hazard score
        combined_score = round(ml_safety_score * 0.40 + empirical_score * 0.60, 1)
    else:
        combined_score = round(empirical_score, 1)

    predicted_safety_score = max(0.0, min(100.0, combined_score))
    risk_level = score_to_risk_level(predicted_safety_score)

    # ── Step 5: Real Hotspot Extraction ──────────────────────────────────────
    risk_hotspots = []
    for h in hotspots_raw[:10]:
        h_fatal = h.get("fatal_count", 0)
        h_accidents = h.get("accident_count", 0)
        h_sev_summary = h.get("severity_summary", {})

        # Determine prominent severity
        if h_fatal > 0:
            prominent_sev = "Fatal"
        elif "Grievous Injury" in h_sev_summary:
            prominent_sev = "Grievous Injury"
        elif "Simple Injury" in h_sev_summary:
            prominent_sev = "Simple Injury"
        else:
            prominent_sev = "Damage Only"

        # Hotspot risk calculation from cluster density
        hs_risk = round(min(98.0, max(25.0, (h_accidents * 2.5) + (h_fatal * 12.0))), 1)

        risk_hotspots.append({
            "latitude": float(h["lat"]),
            "longitude": float(h["lng"]),
            "severity": prominent_sev,
            "risk_score": hs_risk,
            "nearby_accidents": int(h_accidents),
            "description": f"{h['name']} ({h_fatal} fatal, {h_accidents} total historical records)",
        })

    # ── Step 6: Traffic Intelligence Assessment ──────────────────────────────
    traffic_score: Optional[float] = None
    traffic_source: Optional[str] = None
    expected_delay_min: Optional[float] = None

    try:
        # Run traffic evaluation safely
        def _fetch_traffic():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run,
                            evaluate_route_traffic_intelligence(
                                effective_waypoints,
                                distance_km=float(distance_km or 0.0),
                                duration_min=float(duration_min or 0.0),
                                tomtom_api_key=settings.TOMTOM_API_KEY,
                                db=db,
                            ),
                        )
                        return future.result(timeout=10)
                else:
                    return loop.run_until_complete(
                        evaluate_route_traffic_intelligence(
                            effective_waypoints,
                            distance_km=float(distance_km or 0.0),
                            duration_min=float(duration_min or 0.0),
                            tomtom_api_key=settings.TOMTOM_API_KEY,
                            db=db,
                        )
                    )
            except Exception as e:
                logger.warning(f"Traffic intelligence evaluation fallback: {e}")
                return None

        ti_result = _fetch_traffic()
        if ti_result and ti_result.get("traffic_source") not in (None, "unavailable", "no_waypoints"):
            traffic_score = ti_result.get("traffic_score")
            traffic_source = ti_result.get("traffic_source")
            expected_delay_min = ti_result.get("expected_delay_minutes")
    except Exception as exc:
        logger.warning(f"Failed to compute traffic intelligence for route: {exc}")

    traffic_risk_level = determine_traffic_risk_level(traffic_score, traffic_source)

    # ── Step 7: Deterministic Descriptive Factors ────────────────────────────
    factors = []
    if model_loaded and top_predicted_severities:
        most_common_sev = max(top_predicted_severities.items(), key=lambda x: x[1])[0]
        factors.append(f"XGBoost classifier predicted {most_common_sev} as dominant baseline severity profile.")

    if total_accidents > 0:
        factors.append(
            f"Historical accident exposure: {accident_exposure_level} with {total_accidents} recorded incidents near route ({fatal_accidents} fatal)."
        )
    else:
        factors.append("No historical accident records within 300m buffer of route waypoints.")

    if active_hazards > 0:
        factors.append(f"Route crosses {active_hazards} active user-reported road hazard(s).")
    else:
        factors.append("Zero active user-reported road hazards on this route.")

    if traffic_risk_level != "UNKNOWN":
        factors.append(f"Traffic congestion risk is {traffic_risk_level} (traffic score: {traffic_score}/100).")
    else:
        factors.append("Real-time traffic flow/prediction data is currently unavailable for this corridor.")

    return {
        "predicted_safety_score": predicted_safety_score,
        "risk_level": risk_level,
        "accident_exposure": {
            "level": accident_exposure_level,
            "nearby_accidents": total_accidents,
            "severe_accidents": severe_accidents,
        },
        "traffic_risk": {
            "level": traffic_risk_level,
            "traffic_score": traffic_score,
            "traffic_source": traffic_source,
            "expected_delay_minutes": expected_delay_min,
        },
        "risk_hotspots": risk_hotspots,
        "factors": factors,
        "model_used": model_name,
    }
