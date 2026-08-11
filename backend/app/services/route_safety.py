"""
Route Safety Evaluation Service
Empirical route safety scoring and accident hotspot analysis using historical accident data.
"""

import math
from typing import List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from ..models.accident import AccidentData

SEVERITY_WEIGHTS = {
    "Fatal": 1.0,
    "Grievous Injury": 0.75,
    "Simple Injury": 0.5,
    "Damage Only": 0.25,
}

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    R = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def decimate_waypoints(waypoints: List[List[float]], target_spacing_km: float = 0.5) -> List[Tuple[float, float]]:
    """
    Decimate route waypoints so points are roughly target_spacing_km apart.
    Reduces redundant spatial DB queries while retaining geometric coverage.
    """
    if not waypoints:
        return []
    
    sampled = [(float(waypoints[0][0]), float(waypoints[0][1]))]
    accumulated_dist = 0.0

    for i in range(1, len(waypoints)):
        prev_lat, prev_lng = waypoints[i - 1]
        curr_lat, curr_lng = waypoints[i]
        dist = haversine_distance(prev_lat, prev_lng, curr_lat, curr_lng)
        accumulated_dist += dist

        if accumulated_dist >= target_spacing_km:
            sampled.append((float(curr_lat), float(curr_lng)))
            accumulated_dist = 0.0

    # Ensure last waypoint is included if not already
    last_pt = (float(waypoints[-1][0]), float(waypoints[-1][1]))
    if sampled[-1] != last_pt:
        sampled.append(last_pt)

    return sampled

def evaluate_route_safety(
    db: Session,
    waypoints: List[List[float]],
    search_radius_km: float = 0.3,
) -> Dict[str, Any]:
    """
    Evaluates empirical route safety by querying historical accident records within
    a search radius around decimated route waypoints.
    """
    if not waypoints or len(waypoints) < 2:
        return {
            "empirical_safety_score": 90.0,
            "total_accidents_nearby": 0,
            "fatal_accidents_nearby": 0,
            "hotspots": [],
        }

    sampled_points = decimate_waypoints(waypoints, target_spacing_km=0.4)
    
    # Calculate bounding box covering the sampled points with a buffer (~0.01 deg ~= 1.1km)
    min_lat = min(p[0] for p in sampled_points) - 0.01
    max_lat = max(p[0] for p in sampled_points) + 0.01
    min_lng = min(p[1] for p in sampled_points) - 0.01
    max_lng = max(p[1] for p in sampled_points) + 0.01

    # Single spatial query for all accidents inside the route's overall bounding box
    accidents_in_bbox = (
        db.query(
            AccidentData.latitude,
            AccidentData.longitude,
            AccidentData.severity,
            AccidentData.district,
            AccidentData.accident_road,
            AccidentData.main_cause,
        )
        .filter(
            AccidentData.latitude.between(min_lat, max_lat),
            AccidentData.longitude.between(min_lng, max_lng),
        )
        .limit(2000)
        .all()
    )

    if not accidents_in_bbox:
        return {
            "empirical_safety_score": 95.0,
            "total_accidents_nearby": 0,
            "fatal_accidents_nearby": 0,
            "hotspots": [],
        }

    # Filter accidents within search_radius_km of any sampled route waypoint
    matched_accidents = []
    hotspot_grid: Dict[str, dict] = {}
    GRID_SIZE = 0.005  # ~500m grid clustering

    total_weighted_severity = 0.0
    fatal_count = 0

    for acc in accidents_in_bbox:
        acc_lat, acc_lng = acc.latitude, acc.longitude
        # Check distance to nearest sampled waypoint
        is_near_route = any(
            haversine_distance(acc_lat, acc_lng, wp_lat, wp_lng) <= search_radius_km
            for wp_lat, wp_lng in sampled_points
        )

        if is_near_route:
            matched_accidents.append(acc)
            sev = acc.severity or "Unknown"
            weight = SEVERITY_WEIGHTS.get(sev, 0.4)
            total_weighted_severity += weight

            if sev == "Fatal":
                fatal_count += 1

            # Grid key for hotspot grouping
            grid_key = f"{round(acc_lat / GRID_SIZE) * GRID_SIZE:.3f}_{round(acc_lng / GRID_SIZE) * GRID_SIZE:.3f}"
            if grid_key not in hotspot_grid:
                hotspot_grid[grid_key] = {
                    "lats": [],
                    "lngs": [],
                    "district": acc.district or "Unknown",
                    "road": acc.accident_road or "Unknown Location",
                    "severities": {},
                    "count": 0,
                }
            
            node = hotspot_grid[grid_key]
            node["lats"].append(acc_lat)
            node["lngs"].append(acc_lng)
            node["count"] += 1
            node["severities"][sev] = node["severities"].get(sev, 0) + 1

    total_matched = len(matched_accidents)

    # Compute Empirical Safety Score (0 to 100)
    # Higher weighted accident density -> lower safety score
    # Base 100 penalty formula calibrated for route evaluation:
    penalty = (total_weighted_severity * 1.5) + (fatal_count * 3.0)
    safety_score = max(35.0, min(98.0, round(100.0 - penalty, 1)))

    # Process hotspots (only clusters with 3+ accidents near the route)
    hotspots = []
    for key, data in hotspot_grid.items():
        if data["count"] < 3:
            continue

        center_lat = sum(data["lats"]) / len(data["lats"])
        center_lng = sum(data["lngs"]) / len(data["lngs"])
        fatals = data["severities"].get("Fatal", 0)
        
        if fatals > 2 or data["count"] >= 15:
            risk_level = "critical"
        elif fatals > 0 or data["count"] >= 8:
            risk_level = "high"
        else:
            risk_level = "medium"

        hotspots.append({
            "name": f"{data['district']} - {data['road'] if data['road'] != 'Unknown Location' else 'Accident Zone'}",
            "lat": round(center_lat, 6),
            "lng": round(center_lng, 6),
            "accident_count": data["count"],
            "fatal_count": fatals,
            "severity_summary": data["severities"],
            "risk_level": risk_level,
        })

    # Sort hotspots by accident count descending, top 10
    hotspots.sort(key=lambda h: h["accident_count"], reverse=True)
    hotspots = hotspots[:10]

    # Evaluate live hazards
    hazards_res = evaluate_route_live_hazards(db, waypoints, search_radius_km)
    live_penalty = hazards_res["safety_penalty"]
    
    # Combined score, capped between 20.0 and 98.0
    combined_safety_score = max(20.0, min(98.0, round(safety_score - live_penalty, 1)))

    return {
        "empirical_safety_score": combined_safety_score,
        "total_accidents_nearby": total_matched,
        "fatal_accidents_nearby": fatal_count,
        "hotspots": hotspots,
        "active_hazards_nearby": hazards_res["active_hazards_nearby"],
        "live_hazards": hazards_res["live_hazards"],
        "live_hazard_delay_minutes": hazards_res["delay_minutes"],
    }


def evaluate_route_live_hazards(
    db: Session,
    waypoints: List[List[float]],
    search_radius_km: float = 0.3,
) -> Dict[str, Any]:
    """
    Queries active user-reported hazards within the route bounding box
    and filters those within the search radius of the waypoints.
    """
    if not waypoints or len(waypoints) < 2:
        return {
            "active_hazards_nearby": 0,
            "live_hazards": [],
            "safety_penalty": 0.0,
            "delay_minutes": 0.0
        }

    sampled_points = decimate_waypoints(waypoints, target_spacing_km=0.4)
    
    # Calculate bounding box covering the sampled points with a buffer (~0.01 deg ~= 1.1km)
    min_lat = min(p[0] for p in sampled_points) - 0.01
    max_lat = max(p[0] for p in sampled_points) + 0.01
    min_lng = min(p[1] for p in sampled_points) - 0.01
    max_lng = max(p[1] for p in sampled_points) + 0.01

    from ..models.road_hazard import RoadHazard  # Late import to avoid cyclic import issues

    active_hazards = (
        db.query(RoadHazard)
        .filter(
            RoadHazard.status == "Active",
            RoadHazard.latitude.between(min_lat, max_lat),
            RoadHazard.longitude.between(min_lng, max_lng),
        )
        .all()
    )

    if not active_hazards:
        return {
            "active_hazards_nearby": 0,
            "live_hazards": [],
            "safety_penalty": 0.0,
            "delay_minutes": 0.0
        }

    matched_hazards = []
    safety_penalty = 0.0
    delay_minutes = 0.0

    severity_penalties = {
        "Critical": 15.0,
        "High": 10.0,
        "Medium": 5.0,
        "Low": 2.0,
    }

    # Applied only to hazard types representing a real obstruction (e.g. Accident, Blocked, etc.)
    type_delays = {
        "Road blocked": {"Critical": 15.0, "High": 10.0, "Medium": 6.0, "Low": 3.0},
        "Accident": {"Critical": 10.0, "High": 7.0, "Medium": 4.0, "Low": 2.0},
        "Heavy traffic": {"Critical": 10.0, "High": 7.0, "Medium": 4.0, "Low": 2.0},
        "Road construction": {"Critical": 8.0, "High": 5.0, "Medium": 3.0, "Low": 1.0},
        "Waterlogging": {"Critical": 8.0, "High": 5.0, "Medium": 3.0, "Low": 1.0},
    }

    for h in active_hazards:
        h_lat, h_lng = h.latitude, h.longitude
        is_near_route = any(
            haversine_distance(h_lat, h_lng, wp_lat, wp_lng) <= search_radius_km
            for wp_lat, wp_lng in sampled_points
        )

        if is_near_route:
            matched_hazards.append({
                "id": h.id,
                "hazard_type": h.hazard_type,
                "severity": h.severity,
                "latitude": h.latitude,
                "longitude": h.longitude,
                "description": h.description,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            })

            # Always apply safety penalty
            safety_penalty += severity_penalties.get(h.severity, 5.0)

            # Apply ETA delay ONLY if the hazard type represents a real obstruction
            if h.hazard_type in type_delays:
                severity_map = type_delays[h.hazard_type]
                delay_minutes += severity_map.get(h.severity, 2.0)

    return {
        "active_hazards_nearby": len(matched_hazards),
        "live_hazards": matched_hazards,
        "safety_penalty": safety_penalty,
        "delay_minutes": round(delay_minutes, 1)
    }
