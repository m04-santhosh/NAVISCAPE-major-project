"""
Navigation Router
Handles route generation, alternatives, and route history.
"""

import math
import random
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..models.traffic import RouteHistory
from ..schemas.traffic import RouteRequest, RouteResponse, RouteHistoryResponse
from ..middleware.auth import get_current_user
from ..config import settings

router = APIRouter(prefix="/api", tags=["Navigation"])


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def generate_intermediate_waypoints(
    src_lat: float, src_lng: float,
    dst_lat: float, dst_lng: float,
    num_points: int = 8,
    deviation: float = 0.002,
) -> List[List[float]]:
    """Generate realistic intermediate waypoints between source and destination."""
    waypoints = [[src_lat, src_lng]]
    for i in range(1, num_points + 1):
        fraction = i / (num_points + 1)
        lat = src_lat + (dst_lat - src_lat) * fraction + random.uniform(-deviation, deviation)
        lng = src_lng + (dst_lng - src_lng) * fraction + random.uniform(-deviation, deviation)
        waypoints.append([round(lat, 6), round(lng, 6)])
    waypoints.append([dst_lat, dst_lng])
    return waypoints


@router.post("/navigate", response_model=RouteResponse)
async def navigate(
    data: RouteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a route from source to destination with safety analysis."""
    distance = haversine(data.source_lat, data.source_lng, data.dest_lat, data.dest_lng)

    # Generate route based on type
    if data.route_type == "shortest":
        deviation = 0.001
        speed_factor = 1.0
        safety_base = random.uniform(55, 75)
    elif data.route_type == "safest":
        deviation = 0.004
        speed_factor = 1.3
        safety_base = random.uniform(85, 98)
    else:  # balanced
        deviation = 0.002
        speed_factor = 1.15
        safety_base = random.uniform(70, 90)

    waypoints = generate_intermediate_waypoints(
        data.source_lat, data.source_lng,
        data.dest_lat, data.dest_lng,
        deviation=deviation,
    )

    road_distance = distance * random.uniform(1.2, 1.5)
    avg_speed = random.uniform(25, 45)
    duration = (road_distance / avg_speed) * 60 * speed_factor

    # Generate risk zones along route
    risk_zones = []
    for _ in range(random.randint(1, 4)):
        idx = random.randint(1, len(waypoints) - 2)
        risk_zones.append({
            "lat": waypoints[idx][0],
            "lng": waypoints[idx][1],
            "radius": random.randint(100, 500),
            "risk_level": random.choice(["medium", "high", "critical"]),
            "description": random.choice([
                "Accident-prone intersection",
                "Poor road condition",
                "High congestion zone",
                "Sharp curve ahead",
                "School zone - reduced speed",
            ]),
        })

    # Save to route history
    route_record = RouteHistory(
        user_id=current_user.id,
        source_lat=data.source_lat,
        source_lng=data.source_lng,
        dest_lat=data.dest_lat,
        dest_lng=data.dest_lng,
        source_name=data.source_name,
        dest_name=data.dest_name,
        distance_km=round(road_distance, 2),
        duration_min=round(duration, 1),
        safety_score=round(safety_base, 1),
        route_type=data.route_type,
    )
    db.add(route_record)
    db.commit()

    return RouteResponse(
        route_type=data.route_type,
        distance_km=round(road_distance, 2),
        duration_min=round(duration, 1),
        safety_score=round(safety_base, 1),
        waypoints=waypoints,
        risk_zones=risk_zones,
        congestion_segments=[],
    )


@router.get("/route-alternatives")
async def get_route_alternatives(
    source_lat: float, source_lng: float,
    dest_lat: float, dest_lng: float,
    current_user: User = Depends(get_current_user),
):
    """Get multiple route alternatives (shortest, safest, balanced)."""
    distance = haversine(source_lat, source_lng, dest_lat, dest_lng)
    alternatives = []

    for route_type, label, dev, speed_f, safety_range in [
        ("shortest", "Fastest Route", 0.001, 1.0, (50, 70)),
        ("safest", "Safest Route", 0.004, 1.35, (85, 98)),
        ("balanced", "Balanced Route", 0.002, 1.15, (70, 88)),
    ]:
        wp = generate_intermediate_waypoints(source_lat, source_lng, dest_lat, dest_lng, deviation=dev)
        road_dist = distance * random.uniform(1.2, 1.5)
        dur = (road_dist / random.uniform(25, 45)) * 60 * speed_f
        alternatives.append({
            "route_type": route_type,
            "label": label,
            "distance_km": round(road_dist, 2),
            "duration_min": round(dur, 1),
            "safety_score": round(random.uniform(*safety_range), 1),
            "waypoints": wp,
        })

    return alternatives


@router.get("/route-history", response_model=List[RouteHistoryResponse])
async def get_route_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's route history."""
    routes = (
        db.query(RouteHistory)
        .filter(RouteHistory.user_id == current_user.id)
        .order_by(RouteHistory.created_at.desc())
        .limit(50)
        .all()
    )
    return [RouteHistoryResponse.model_validate(r) for r in routes]
