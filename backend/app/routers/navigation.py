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
from ..schemas.traffic import RouteRequest, RouteHistoryResponse
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/api", tags=["Navigation"])


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
