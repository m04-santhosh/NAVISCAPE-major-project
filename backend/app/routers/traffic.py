"""
Traffic Router
Provides current, historical, and heatmap traffic data.
Also proxies real-time TomTom traffic flow tiles server-side.
Phase 5: Adds POST /api/traffic/evaluate-route for route-specific traffic intelligence.
"""

import random
from datetime import datetime, timedelta
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.traffic import TrafficData
from ..middleware.auth import get_current_user
from ..config import settings
from ..schemas.traffic import RouteTrafficRequest, RouteTrafficResponse
from ..services.traffic_intelligence import evaluate_route_traffic_intelligence

router = APIRouter(prefix="/api/traffic", tags=["Traffic"])

# ---------------------------------------------------------------------------
# TomTom real-time traffic tile proxy
# ---------------------------------------------------------------------------
TOMTOM_TILE_BASE = "https://api.tomtom.com/maps/orbis/traffic/flow/raster/tile"
TOMTOM_TIMEOUT = 10.0  # seconds


@router.get("/tile/{zoomLevel}/{x}/{y}", tags=["Traffic Tiles"])
async def get_traffic_tile(
    zoomLevel: int = Path(..., ge=0, le=22, description="Zoom level (0-22)"),
    x: int = Path(..., ge=0, description="Tile X coordinate"),
    y: int = Path(..., ge=0, description="Tile Y coordinate"),
):
    """
    Proxy endpoint: fetches a real-time TomTom traffic flow raster tile
    and returns the PNG bytes. The TomTom API key is kept server-side only.
    """
    api_key = settings.TOMTOM_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="TomTom API key is not configured on the server. "
                   "Set TOMTOM_API_KEY in backend/.env",
        )

    url = f"{TOMTOM_TILE_BASE}/{zoomLevel}/{x}/{y}"
    params = {"tileSize": 256, "apiVersion": 2}
    headers = {
        "TomTom-Api-Version": "2",
        "TomTom-Api-Key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=TOMTOM_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TomTom tile request timed out")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"TomTom request error: {exc}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"TomTom upstream error {resp.status_code}: {resp.text[:200]}",
        )

    return Response(content=resp.content, media_type="image/png")


# Bangalore junction coordinates
JUNCTIONS = {
    1: {"name": "Silk Board Junction", "lat": 12.9170, "lng": 77.6230},
    2: {"name": "Hebbal Flyover", "lat": 13.0358, "lng": 77.5970},
    3: {"name": "KR Puram Junction", "lat": 13.0012, "lng": 77.6960},
    4: {"name": "Marathahalli Bridge", "lat": 12.9591, "lng": 77.7010},
    5: {"name": "Whitefield Junction", "lat": 12.9698, "lng": 77.7500},
    6: {"name": "Banashankari Circle", "lat": 12.9255, "lng": 77.5468},
    7: {"name": "Jayanagar 4th Block", "lat": 12.9260, "lng": 77.5830},
    8: {"name": "MG Road Metro", "lat": 12.9756, "lng": 77.6066},
}


def simulate_traffic(junction_id: int, hour: int, day: int) -> dict:
    """Simulate realistic traffic data based on time patterns."""
    base_count = random.randint(80, 200)

    # Rush hour multiplier
    if hour in [8, 9, 17, 18, 19]:
        base_count = int(base_count * random.uniform(2.0, 3.0))
    elif hour in [7, 10, 16, 20]:
        base_count = int(base_count * random.uniform(1.5, 2.0))
    elif hour in [0, 1, 2, 3, 4, 5]:
        base_count = int(base_count * random.uniform(0.1, 0.3))

    # Weekend reduction
    if day >= 5:
        base_count = int(base_count * 0.7)

    # Junction-specific multiplier (Silk Board is always busier)
    if junction_id == 1:
        base_count = int(base_count * 1.5)

    avg_speed = max(5, 60 - (base_count / 10) + random.uniform(-5, 5))

    if base_count > 400:
        congestion = "critical"
    elif base_count > 250:
        congestion = "high"
    elif base_count > 150:
        congestion = "medium"
    else:
        congestion = "low"

    return {
        "vehicle_count": base_count,
        "avg_speed": round(avg_speed, 1),
        "congestion_level": congestion,
    }


@router.get("/current")
async def get_current_traffic(current_user=Depends(get_current_user)):
    """Get simulated current traffic data for all junctions."""
    now = datetime.now()
    results = []

    for jid, info in JUNCTIONS.items():
        traffic = simulate_traffic(jid, now.hour, now.weekday())
        results.append({
            "junction_id": jid,
            "junction_name": info["name"],
            "latitude": info["lat"],
            "longitude": info["lng"],
            "timestamp": now.isoformat(),
            **traffic,
        })

    return results


@router.get("/historical")
async def get_historical_traffic(
    junction_id: int = Query(1, ge=1, le=8),
    days: int = Query(7, ge=1, le=30),
    current_user=Depends(get_current_user),
):
    """Get simulated historical traffic data for a junction."""
    now = datetime.now()
    results = []

    for day_offset in range(days, 0, -1):
        for hour in range(24):
            dt = now - timedelta(days=day_offset, hours=now.hour - hour)
            traffic = simulate_traffic(junction_id, hour, dt.weekday())
            results.append({
                "timestamp": dt.replace(hour=hour, minute=0, second=0).isoformat(),
                "hour": hour,
                "day_of_week": dt.weekday(),
                **traffic,
            })

    return results


@router.get("/heatmap")
async def get_traffic_heatmap(current_user=Depends(get_current_user)):
    """Get traffic density heatmap data points across Bangalore."""
    now = datetime.now()
    points = []

    # Generate points around each junction
    for jid, info in JUNCTIONS.items():
        traffic = simulate_traffic(jid, now.hour, now.weekday())
        intensity = min(1.0, traffic["vehicle_count"] / 500)

        # Add cluster of points around the junction
        for _ in range(random.randint(5, 15)):
            points.append({
                "lat": info["lat"] + random.uniform(-0.008, 0.008),
                "lng": info["lng"] + random.uniform(-0.008, 0.008),
                "intensity": round(intensity * random.uniform(0.6, 1.0), 3),
            })

    # Add random road points
    for _ in range(50):
        points.append({
            "lat": random.uniform(12.85, 13.08),
            "lng": random.uniform(77.48, 77.78),
            "intensity": round(random.uniform(0.1, 0.5), 3),
        })

    return points


@router.get("/junctions")
async def get_junctions(current_user=Depends(get_current_user)):
    """Get all monitored junction locations."""
    return [
        {"id": jid, **info}
        for jid, info in JUNCTIONS.items()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5: Route-specific Traffic Intelligence
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/evaluate-route", response_model=RouteTrafficResponse, tags=["Traffic Intelligence"])
async def evaluate_route_traffic(
    body: RouteTrafficRequest,
    current_user=Depends(get_current_user),
):
    """
    Phase 5 — Route Traffic Intelligence.
    Evaluates real-time and predicted traffic conditions for a given set of route waypoints.

    Uses:
    - TomTom Traffic Flow Segment API (real-time speed vs free-flow speed per coordinate)
    - LSTM model for junction 1 (Silk Board) when model file is present on disk
    - Hour-pattern prediction model for all other monitored junctions on the route

    Falls back to junction-proximity scoring when TomTom is unavailable.
    Navigation never crashes — all errors produce a safe neutral response.
    """
    result = await evaluate_route_traffic_intelligence(
        waypoints=body.waypoints,
        distance_km=body.distance_km,
        duration_min=body.duration_min,
        tomtom_api_key=settings.TOMTOM_API_KEY,
        prediction_horizon_minutes=body.prediction_horizon_minutes,
    )
    return RouteTrafficResponse(**result)
