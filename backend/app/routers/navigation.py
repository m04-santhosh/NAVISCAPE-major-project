"""
Navigation Router
Handles route saving and route history.
Routing is handled on the frontend via OSRM API.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..models.traffic import RouteHistory
from ..schemas.traffic import (
    RouteRequest,
    RouteHistoryResponse,
    RouteEvaluationRequest,
    RouteEvaluationResponse,
    OptimizeRoutesRequest,
    OptimizeRoutesResponse,
)
from ..middleware.auth import get_current_user
from ..services.route_safety import evaluate_route_safety
from ..services.route_optimizer import optimize_candidate_routes

router = APIRouter(prefix="/api", tags=["Navigation"])


@router.post("/navigation/optimize-routes", response_model=OptimizeRoutesResponse)
async def optimize_routes(
    data: OptimizeRoutesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Phase 4: Smart Route Decision Engine.
    Evaluates candidate routes using safety, accident risk, real-time traffic, relative ETA, and distance.
    Calculates unified 0-100 overall score and selects recommended route with dynamic reasons.
    """
    raw_routes = [r.model_dump() for r in data.routes]
    res = optimize_candidate_routes(db, raw_routes)
    return OptimizeRoutesResponse(**res)



@router.post("/navigation/evaluate-route", response_model=RouteEvaluationResponse)
async def evaluate_route(
    data: RouteEvaluationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Evaluate empirical route safety using historical accident data along route waypoints.
    Calculates 0-100 safety score, nearby accident count, fatal count, and hotspots.
    """
    if not data.waypoints:
        return RouteEvaluationResponse(
            route_type=data.route_type,
            empirical_safety_score=90.0,
            total_accidents_nearby=0,
            fatal_accidents_nearby=0,
            hotspots=[],
        )

    res = evaluate_route_safety(db, waypoints=data.waypoints)
    return RouteEvaluationResponse(
        route_type=data.route_type,
        empirical_safety_score=res["empirical_safety_score"],
        total_accidents_nearby=res["total_accidents_nearby"],
        fatal_accidents_nearby=res["fatal_accidents_nearby"],
        hotspots=res["hotspots"],
        active_hazards_nearby=res.get("active_hazards_nearby", 0),
        live_hazards=res.get("live_hazards", []),
    )


@router.post("/navigate")
async def navigate(
    data: RouteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a navigated route to history. Route geometry comes from OSRM on the frontend."""
    route_record = RouteHistory(
        user_id=current_user.id,
        source_lat=data.source_lat,
        source_lng=data.source_lng,
        dest_lat=data.dest_lat,
        dest_lng=data.dest_lng,
        source_name=data.source_name,
        dest_name=data.dest_name,
        distance_km=data.distance_km,
        duration_min=data.duration_min,
        safety_score=data.safety_score,
        route_type=data.route_type,
    )
    db.add(route_record)
    db.commit()

    return {"message": "Route saved", "route_type": data.route_type}


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

