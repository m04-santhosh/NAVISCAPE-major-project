"""
Route Optimizer Service for NAVISCAPE Phase 4 + Phase 5
Centralized route scoring engine combining empirical safety scores, historical accident risk,
traffic congestion (Phase 5: TomTom Flow + LSTM/hour-pattern prediction),
relative ETA, and distance.
"""

import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from .route_safety import evaluate_route_safety
from .traffic_intelligence import evaluate_route_traffic_intelligence
from ..config import settings

# Centralized configurable scoring weights (must sum to 1.0)
DEFAULT_WEIGHTS = {
    "safety": 0.40,
    "traffic": 0.30,
    "eta": 0.20,
    "distance": 0.10,
}





def compute_authoritative_eta(
    duration_min: float,
    traffic_delay_minutes: float = 0.0,
    hazard_delay_minutes: float = 0.0,
) -> Dict[str, float]:
    """
    Computes mathematically consistent authoritative ETA components.
    Guarantees:
      duration_min = base OSRM duration in minutes
      traffic_delay_minutes = delay from real TomTom flow / LSTM
      hazard_delay_minutes = delay from active road hazards
      expected_delay_minutes = traffic_delay_minutes + hazard_delay_minutes
      eta_minutes = duration_min + expected_delay_minutes
    """
    base = round(max(0.0, float(duration_min or 0.0)), 1)
    traffic = round(max(0.0, float(traffic_delay_minutes or 0.0)), 1)
    hazard = round(max(0.0, float(hazard_delay_minutes or 0.0)), 1)
    expected_delay = round(traffic + hazard, 1)
    eta = round(base + expected_delay, 1)
    return {
        "duration_min": base,
        "traffic_delay_minutes": traffic,
        "hazard_delay_minutes": hazard,
        "expected_delay_minutes": expected_delay,
        "eta_minutes": eta,
    }


def optimize_candidate_routes(
    db: Session,
    routes: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Phase 4 + Phase 5 + Phase 12: Optimizes and scores candidate routes using safety, traffic intelligence
    (TomTom Flow + LSTM predictions), relative ETA, and distance.
    Returns detailed route evaluations and a recommended route with dynamic reasons.
    """
    if not routes:
        return {
            "routes": [],
            "recommended_route_id": "",
            "recommendation_reasons": ["No candidate routes provided"],
        }

    active_weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    total_w = sum(active_weights.values()) or 1.0
    w_safety = active_weights["safety"] / total_w
    w_traffic = active_weights["traffic"] / total_w
    w_eta = active_weights["eta"] / total_w
    w_distance = active_weights["distance"] / total_w

    evaluated_list = []
    durations = []
    distances = []

    def _get_traffic(waypoints, distance_km, duration_min):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        evaluate_route_traffic_intelligence(
                            waypoints,
                            distance_km=distance_km,
                            duration_min=duration_min,
                            tomtom_api_key=settings.TOMTOM_API_KEY,
                            db=db,
                        ),
                    )
                    return future.result(timeout=15)
            else:
                return loop.run_until_complete(
                    evaluate_route_traffic_intelligence(
                        waypoints,
                        distance_km=distance_km,
                        duration_min=duration_min,
                        tomtom_api_key=settings.TOMTOM_API_KEY,
                        db=db,
                    )
                )
        except Exception:
            return {
                "traffic_score": 70.0,
                "current_traffic_score": 70.0,
                "predicted_traffic_score": None,
                "traffic_level": "Moderate",
                "predicted_congestion": None,
                "expected_delay_minutes": 0.0,
                "traffic_source": "unavailable",
                "traffic_confidence": 0.0,
                "prediction_available": False,
                "prediction_horizon_minutes": 30,
                "junctions_on_route": [],
            }

    # Step 1: Gather safety + traffic intelligence for all routes
    for idx, r in enumerate(routes):
        route_id = str(r.get("route_id") or r.get("route_type") or f"route_{idx}")
        route_type = str(r.get("route_type") or "balanced")
        waypoints = r.get("waypoints") or []
        distance_km = float(r.get("distance_km") or 0.0)
        duration_min = float(r.get("duration_min") or 0.0)

        # 1. Empirical Safety Score (Phase 3)
        safety_res = evaluate_route_safety(db, waypoints=waypoints)
        safety_score = float(safety_res.get("empirical_safety_score", 85.0))
        accident_risk_score = round(max(0.0, min(100.0, 100.0 - safety_score)), 1)
        total_accidents = int(safety_res.get("total_accidents_nearby", 0))
        fatal_accidents = int(safety_res.get("fatal_accidents_nearby", 0))
        hotspots = safety_res.get("hotspots", [])

        # 2. Phase 5 Traffic Intelligence
        ti = _get_traffic(waypoints, distance_km, duration_min)
        traffic_score = ti["traffic_score"]
        traffic_level = ti["traffic_level"]
        current_traffic_score = ti["current_traffic_score"]
        predicted_traffic_score = ti["predicted_traffic_score"]
        predicted_congestion = ti["predicted_congestion"]
        traffic_delay_raw = float(ti.get("expected_delay_minutes") or 0.0)
        traffic_source = ti["traffic_source"]
        traffic_confidence = ti["traffic_confidence"]
        prediction_available = ti["prediction_available"]
        prediction_horizon_minutes = ti["prediction_horizon_minutes"]

        # Extract active hazards and hazard delay
        active_hazards_count = int(safety_res.get("active_hazards_nearby", 0))
        live_hazards_list = safety_res.get("live_hazards", [])
        hazard_delay_raw = float(safety_res.get("live_hazard_delay_minutes", 0.0))

        # Authoritative ETA calculation (single backend source of truth)
        eta_data = compute_authoritative_eta(
            duration_min=duration_min,
            traffic_delay_minutes=traffic_delay_raw,
            hazard_delay_minutes=hazard_delay_raw,
        )

        eta_minutes = eta_data["eta_minutes"]
        durations.append(eta_minutes if eta_minutes > 0 else 1.0)
        distances.append(distance_km if distance_km > 0 else 1.0)

        evaluated_list.append({
            "route_id": route_id,
            "route_type": route_type,
            "distance_km": distance_km,
            "duration_min": eta_data["duration_min"],
            "traffic_delay_minutes": eta_data["traffic_delay_minutes"],
            "hazard_delay_minutes": eta_data["hazard_delay_minutes"],
            "expected_delay_minutes": eta_data["expected_delay_minutes"],
            "eta_minutes": eta_data["eta_minutes"],
            "waypoints": waypoints,
            "safety_score": safety_score,
            "accident_risk_score": accident_risk_score,
            "total_accidents_nearby": total_accidents,
            "fatal_accidents_nearby": fatal_accidents,
            "hotspots": hotspots,
            "active_hazards_nearby": active_hazards_count,
            "live_hazards": live_hazards_list,
            # Traffic intelligence fields
            "traffic_score": traffic_score,
            "current_traffic_score": current_traffic_score,
            "predicted_traffic_score": predicted_traffic_score,
            "traffic_level": traffic_level,
            "predicted_congestion": predicted_congestion,
            "traffic_source": traffic_source,
            "traffic_confidence": traffic_confidence,
            "prediction_available": prediction_available,
            "prediction_horizon_minutes": prediction_horizon_minutes,
        })

    # Step 2: Compute relative ETA and Distance scores
    min_duration = min(durations) if durations else 1.0
    min_distance = min(distances) if distances else 1.0

    max_safety = max(item["safety_score"] for item in evaluated_list)
    max_traffic = max(item["traffic_score"] for item in evaluated_list)

    for item in evaluated_list:
        dur = item["eta_minutes"] if item["eta_minutes"] > 0 else min_duration
        dist = item["distance_km"] if item["distance_km"] > 0 else min_distance

        # Relative ETA score: 100 for fastest, proportional reduction for slower
        eta_score = round(min(100.0, max(10.0, (min_duration / dur) * 100.0)), 1)

        # Relative Distance score: 100 for shortest, proportional reduction for longer
        distance_score = round(min(100.0, max(10.0, (min_distance / dist) * 100.0)), 1)

        item["eta_score"] = eta_score
        item["distance_score"] = distance_score

        # 3. Overall Unified Route Score
        overall = (
            item["safety_score"] * w_safety
            + item["traffic_score"] * w_traffic
            + eta_score * w_eta
            + distance_score * w_distance
        )
        item["overall_score"] = round(min(100.0, max(0.0, overall)), 1)

        # Risk level text
        if item["safety_score"] >= 85.0:
            item["risk_level"] = "Low"
        elif item["safety_score"] >= 70.0:
            item["risk_level"] = "Moderate"
        elif item["safety_score"] >= 50.0:
            item["risk_level"] = "High"
        else:
            item["risk_level"] = "Critical"

    # Step 3: Select Recommended Route (Highest Overall Score)
    sorted_evals = sorted(
        evaluated_list,
        key=lambda x: (x["overall_score"], x["safety_score"], -x["eta_minutes"]),
        reverse=True,
    )
    recommended = sorted_evals[0]
    recommended_id = recommended["route_id"]

    # Step 4: Generate Dynamic Recommendation Reasons
    rec_reasons = []

    # Safety advantages
    if recommended["safety_score"] == max_safety or recommended["safety_score"] >= 85.0:
        rec_reasons.append("✓ Lower accident risk")

    critical_hotspots = [h for h in recommended["hotspots"] if h.get("risk_level") == "critical"]
    if not critical_hotspots:
        rec_reasons.append("✓ No critical accident hotspots")

    # Current traffic advantage
    if recommended["traffic_score"] == max_traffic or recommended["traffic_level"] in ["Low", "Moderate"]:
        rec_reasons.append("✓ Lower current congestion")

    # Phase 5: Predicted traffic advantage
    if recommended.get("prediction_available") and recommended.get("predicted_congestion"):
        pred_cong = recommended["predicted_congestion"]
        horizon = recommended.get("prediction_horizon_minutes", 30)
        if pred_cong in ["Low", "Moderate"]:
            rec_reasons.append(f"✓ Lower predicted congestion in {horizon} min")
        elif pred_cong == "High":
            rec_reasons.append(f"⚠ High predicted congestion in {horizon} min")
        elif pred_cong == "Severe":
            rec_reasons.append(f"⚠ Severe predicted congestion in {horizon} min")

    # Phase 5: Expected delay (includes live user hazard delays)
    if recommended.get("expected_delay_minutes") is not None:
        delay = recommended["expected_delay_minutes"]
        if delay > 2.0:
            rec_reasons.append(f"⚠ Expected +{delay:.0f} min delay from current traffic/hazards")
        else:
            rec_reasons.append("✓ Minimal traffic/hazard delay expected")

    # Phase 7: Live user-reported hazards warning
    active_hazards = recommended.get("active_hazards_nearby", 0)
    if active_hazards > 0:
        rec_reasons.append(f"⚠ Contains {active_hazards} active user hazard report{'s' if active_hazards > 1 else ''}")
    else:
        rec_reasons.append("✓ No active user-reported hazards")

    if recommended["duration_min"] == min_duration:
        rec_reasons.append("✓ Faster ETA")

    if recommended["distance_km"] == min_distance:
        rec_reasons.append("✓ Shorter distance")

    if not rec_reasons:
        rec_reasons.append("✓ Best overall safety and traffic balance")

    # Tradeoff warnings
    if recommended["duration_min"] > min_duration:
        diff_min = int(round(recommended["duration_min"] - min_duration))
        if diff_min > 0:
            # If significantly better predicted traffic, explain the tradeoff
            pred_better = (
                recommended.get("prediction_available")
                and recommended.get("predicted_congestion") in ["Low", "Moderate"]
            )
            if pred_better:
                rec_reasons.append(
                    f"⚠ {diff_min} min slower but significantly lower predicted congestion"
                )
            else:
                rec_reasons.append(f"⚠ {diff_min} minute{'s' if diff_min > 1 else ''} slower than the fastest route")
    elif recommended["distance_km"] > min_distance:
        diff_km = round(recommended["distance_km"] - min_distance, 1)
        if diff_km >= 0.5:
            rec_reasons.append(f"⚠ {diff_km} km longer than the shortest route")

    # Assign dynamic summary reason to each evaluated route
    for item in evaluated_list:
        reasons = []
        if item["route_id"] == recommended_id:
            item["reasons"] = rec_reasons
        else:
            if item["duration_min"] == min_duration:
                reasons.append("Fastest route option")
            if item["distance_km"] == min_distance:
                reasons.append("Shortest physical distance")
            if item["safety_score"] == max_safety:
                reasons.append("Highest empirical safety score")
            if not reasons:
                reasons.append("Alternative route option")
            item["reasons"] = reasons

    return {
        "routes": evaluated_list,
        "recommended_route_id": recommended_id,
        "recommendation_reasons": rec_reasons,
    }
