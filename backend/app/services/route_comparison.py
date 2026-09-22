"""
Predictive Route Comparison Service — NAVISCAPE Phase 3B
Compares multiple actual routing alternatives and generates predictive safety intelligence,
historical accident exposure metrics, traffic flow risks, and objective trade-off summaries.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from .predictive_route_risk import evaluate_predictive_route_risk

logger = logging.getLogger(__name__)

OSRM_ROUTE_BASE = "https://router.project-osrm.org/route/v1/driving"
OSRM_TIMEOUT = 5.0  # seconds


async def fetch_real_osrm_alternatives(
    src_lat: float,
    src_lng: float,
    dst_lat: float,
    dst_lng: float,
) -> List[Dict[str, Any]]:
    """
    Fetches genuine driving routes and alternatives from OSRM.
    Returns parsed list of actual candidate routes with real geometries.
    """
    url = f"{OSRM_ROUTE_BASE}/{src_lng},{src_lat};{dst_lng},{dst_lat}"
    params = {
        "alternatives": "true",
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
    }

    try:
        async with httpx.AsyncClient(timeout=OSRM_TIMEOUT) as client:
            resp = await client.get(url, params=params)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok" and data.get("routes"):
                raw_routes = data["routes"]
                # Sort ascending by distance
                sorted_routes = sorted(raw_routes, key=lambda r: r.get("distance", 0.0))
                type_labels = ["shortest", "balanced", "safest"]

                result_routes = []
                for i, r in enumerate(sorted_routes):
                    rtype = type_labels[min(i, len(type_labels) - 1)]
                    geom = r.get("geometry", {}).get("coordinates", [])
                    # GeoJSON is [lng, lat] -> convert to [lat, lng]
                    waypoints = [[float(c[1]), float(c[0])] for c in geom]
                    dist_km = round(float(r.get("distance", 0.0)) / 1000.0, 2)
                    dur_min = round(float(r.get("duration", 0.0)) / 60.0, 1)

                    result_routes.append({
                        "route_id": f"route_{i + 1}",
                        "route_type": rtype,
                        "distance_km": dist_km,
                        "duration_min": dur_min,
                        "waypoints": waypoints,
                    })
                return result_routes
    except Exception as exc:
        logger.warning(f"OSRM routing request failed/timed out: {exc}")

    # Fallback to single direct line if external routing provider is unreachable
    return [
        {
            "route_id": "route_1",
            "route_type": "direct",
            "distance_km": 0.0,
            "duration_min": 0.0,
            "waypoints": [[src_lat, src_lng], [dst_lat, dst_lng]],
        }
    ]


def compare_predictive_routes(
    db: Session,
    source_lat: float,
    source_lng: float,
    destination_lat: float,
    destination_lng: float,
    candidate_routes: Optional[List[Dict[str, Any]]] = None,
    weather: str = "Clear",
    road_condition: str = "Not Applicable",
    surface_condition: str = "Not Applicable",
) -> Dict[str, Any]:
    """
    Evaluates and compares actual route alternatives.

    Computes:
      - Predictive safety score (0-100) per route using XGBoost + Historical Accidents.
      - Historical accident exposure & severe casualty count per route.
      - Real-time/forecast traffic risk level and expected delays.
      - Objective, non-prescriptive trade-off summary between alternatives.
    """
    # ── Step 1: Obtain Candidate Routes ──────────────────────────────────────
    routes_to_evaluate: List[Dict[str, Any]] = []

    if candidate_routes and len(candidate_routes) > 0:
        for i, cr in enumerate(candidate_routes):
            r_id = cr.get("route_id") or f"route_{i + 1}"
            r_type = cr.get("route_type") or "balanced"
            dist = float(cr.get("distance_km") or 0.0)
            dur = float(cr.get("duration_min") or 0.0)
            wps = cr.get("waypoints") or [[source_lat, source_lng], [destination_lat, destination_lng]]
            routes_to_evaluate.append({
                "route_id": r_id,
                "route_type": r_type,
                "distance_km": dist,
                "duration_min": dur,
                "waypoints": wps,
            })
    else:
        # Fetch real routes synchronously via event loop / thread pool
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        fetch_real_osrm_alternatives(source_lat, source_lng, destination_lat, destination_lng),
                    )
                    routes_to_evaluate = future.result(timeout=7)
            else:
                routes_to_evaluate = loop.run_until_complete(
                    fetch_real_osrm_alternatives(source_lat, source_lng, destination_lat, destination_lng)
                )
        except Exception as e:
            logger.warning(f"Error fetching OSRM alternatives in route comparison: {e}")
            routes_to_evaluate = [
                {
                    "route_id": "route_1",
                    "route_type": "direct",
                    "distance_km": 0.0,
                    "duration_min": 0.0,
                    "waypoints": [[source_lat, source_lng], [destination_lat, destination_lng]],
                }
            ]

    # ── Step 2: Predictive Risk Evaluation for Each Route ────────────────────
    evaluated_items = []
    distances = []
    durations = []
    safety_scores = []
    accident_counts = []
    traffic_scores = []

    for r in routes_to_evaluate:
        risk_eval = evaluate_predictive_route_risk(
            db=db,
            source_lat=source_lat,
            source_lng=source_lng,
            destination_lat=destination_lat,
            destination_lng=destination_lng,
            waypoints=r.get("waypoints"),
            distance_km=r.get("distance_km"),
            duration_min=r.get("duration_min"),
            weather=weather,
            road_condition=road_condition,
            surface_condition=surface_condition,
        )

        item = {
            "route_id": str(r.get("route_id") or "route_1"),
            "route_type": str(r.get("route_type") or "balanced"),
            "distance_km": float(r.get("distance_km") or 0.0),
            "duration_min": float(r.get("duration_min") or 0.0),
            "predicted_safety_score": risk_eval["predicted_safety_score"],
            "risk_level": risk_eval["risk_level"],
            "accident_exposure": risk_eval["accident_exposure"],
            "traffic_risk": risk_eval["traffic_risk"],
            "risk_hotspots": risk_eval["risk_hotspots"],
            "waypoints": r.get("waypoints") or [],
            "factors": risk_eval["factors"],
        }
        evaluated_items.append(item)

        distances.append(item["distance_km"])
        durations.append(item["duration_min"])
        safety_scores.append(item["predicted_safety_score"])
        accident_counts.append(item["accident_exposure"]["nearby_accidents"])

        tf_score = item["traffic_risk"].get("traffic_score")
        if tf_score is not None:
            traffic_scores.append(tf_score)

    # ── Step 3: Objective Trade-off Analysis ──────────────────────────────────
    alternatives_available = len(evaluated_items) >= 2
    trade_off_summary = None

    if alternatives_available:
        dist_diff = round(max(distances) - min(distances), 2)
        dur_diff = round(max(durations) - min(durations), 1)
        safety_diff = round(max(safety_scores) - min(safety_scores), 1)
        acc_diff = max(accident_counts) - min(accident_counts)
        tf_diff = round(max(traffic_scores) - min(traffic_scores), 1) if traffic_scores else None

        notes = []

        # Find safest and fastest routes
        safest_item = max(evaluated_items, key=lambda x: x["predicted_safety_score"])
        fastest_item = min(evaluated_items, key=lambda x: x["duration_min"] if x["duration_min"] > 0 else 9999)
        shortest_item = min(evaluated_items, key=lambda x: x["distance_km"] if x["distance_km"] > 0 else 9999)

        if safest_item["route_id"] != fastest_item["route_id"] and safety_diff > 0:
            extra_time = round(safest_item["duration_min"] - fastest_item["duration_min"], 1)
            time_phrase = f"+{extra_time} min duration" if extra_time > 0 else "comparable duration"
            notes.append(
                f"Route '{safest_item['route_id']}' provides a +{safety_diff} higher predicted safety score at the trade-off of {time_phrase}."
            )

        if acc_diff > 0:
            notes.append(
                f"Historical accident exposure differs by up to {acc_diff} recorded incidents across alternative paths."
            )

        if dist_diff > 0:
            notes.append(
                f"Physical travel distance varies by {dist_diff} km between the shortest and longest alternatives."
            )

        if tf_diff is not None and tf_diff > 5.0:
            notes.append(
                f"Real-time traffic flow index varies by {tf_diff} points between candidate corridors."
            )

        trade_off_summary = {
            "distance_difference_km": dist_diff,
            "duration_difference_min": dur_diff,
            "safety_score_difference": safety_diff,
            "accident_exposure_difference": acc_diff,
            "traffic_score_difference": tf_diff,
            "tradeoff_notes": notes,
        }

    return {
        "routes": evaluated_items,
        "trade_off_summary": trade_off_summary,
        "alternatives_available": alternatives_available,
        "model_used": "xgboost_severity_classifier",
    }
