"""
Traffic Router
Provides current, historical, and heatmap traffic data.
Also proxies real-time TomTom traffic flow tiles server-side.
Phase 5: Adds POST /api/traffic/evaluate-route for route-specific traffic intelligence.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Union

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


@router.get("/current")
async def get_current_traffic(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current traffic data for all monitored junctions.
    Returns real TomTom traffic observations if collected; otherwise returns structured unavailable response.
    """
    now = datetime.now()
    results = []

    for jid, info in JUNCTIONS.items():
        obs = (
            db.query(TrafficData)
            .filter(TrafficData.junction_id == jid, TrafficData.is_test == False)
            .order_by(TrafficData.timestamp.desc())
            .first()
        )
        if obs:
            cong = obs.congestion_level
            if not cong and obs.speed_ratio is not None:
                if obs.speed_ratio < 0.4:
                    cong = "critical"
                elif obs.speed_ratio < 0.7:
                    cong = "high"
                elif obs.speed_ratio < 0.9:
                    cong = "medium"
                else:
                    cong = "low"

            results.append({
                "junction_id": jid,
                "junction_name": info["name"],
                "latitude": info["lat"],
                "longitude": info["lng"],
                "timestamp": obs.timestamp.isoformat() if obs.timestamp else now.isoformat(),
                "vehicle_count": obs.vehicle_count or 0,
                "avg_speed": obs.avg_speed,
                "free_flow_speed": obs.free_flow_speed,
                "speed_ratio": obs.speed_ratio,
                "congestion_level": cong or "low",
                "data_available": True,
                "data_source": "tomtom_observation",
            })
        else:
            results.append({
                "junction_id": jid,
                "junction_name": info["name"],
                "latitude": info["lat"],
                "longitude": info["lng"],
                "timestamp": now.isoformat(),
                "vehicle_count": None,
                "avg_speed": None,
                "free_flow_speed": None,
                "speed_ratio": None,
                "congestion_level": None,
                "data_available": False,
                "data_source": "unavailable",
                "reason": "Real traffic observations are not available yet",
            })

    return results


@router.get("/historical")
async def get_historical_traffic(
    junction_id: int = Query(1, ge=1, le=8),
    days: int = Query(7, ge=1, le=30),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get historical traffic data for a junction from database observations.
    """
    cutoff = datetime.now() - timedelta(days=days)
    records = (
        db.query(TrafficData)
        .filter(
            TrafficData.junction_id == junction_id,
            TrafficData.is_test == False,
            TrafficData.timestamp >= cutoff
        )
        .order_by(TrafficData.timestamp.asc())
        .all()
    )

    if records:
        return [
            {
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "hour": r.hour_of_day if r.hour_of_day is not None else (r.timestamp.hour if r.timestamp else 0),
                "day_of_week": r.day_of_week if r.day_of_week is not None else (r.timestamp.weekday() if r.timestamp else 0),
                "vehicle_count": r.vehicle_count,
                "avg_speed": r.avg_speed,
                "free_flow_speed": r.free_flow_speed,
                "speed_ratio": r.speed_ratio,
                "congestion_level": r.congestion_level or ("critical" if r.speed_ratio and r.speed_ratio < 0.4 else "high" if r.speed_ratio and r.speed_ratio < 0.7 else "medium" if r.speed_ratio and r.speed_ratio < 0.9 else "low"),
                "data_available": True,
                "data_source": "tomtom_observation",
            }
            for r in records
        ]

    return {
        "data_available": False,
        "data_source": "unavailable",
        "reason": "Real historical traffic observations are not available yet",
        "results": [],
    }


@router.get("/heatmap")
async def get_traffic_heatmap(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get traffic density heatmap data points across Bangalore from real observations."""
    cutoff = datetime.now() - timedelta(hours=24)
    records = (
        db.query(TrafficData)
        .filter(TrafficData.is_test == False, TrafficData.timestamp >= cutoff)
        .order_by(TrafficData.timestamp.desc())
        .limit(200)
        .all()
    )

    points = []
    for r in records:
        if r.latitude and r.longitude and r.speed_ratio is not None:
            intensity = round(1.0 - float(r.speed_ratio), 3)
            points.append({
                "lat": r.latitude,
                "lng": r.longitude,
                "intensity": max(0.1, min(1.0, intensity)),
                "data_source": "tomtom_observation",
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


@router.post("/collect", tags=["Traffic Intelligence"])
async def trigger_traffic_collection(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually triggers a TomTom traffic collection run immediately.
    Collects speeds for all 8 monitored junctions and saves them in the database.
    """
    from ..services.traffic_collector import fetch_and_store_junction_traffic
    stored_count = await fetch_and_store_junction_traffic(db)
    return {
        "status": "success",
        "message": f"Successfully completed collection run. Stored {stored_count} observations.",
        "stored_count": stored_count,
    }
