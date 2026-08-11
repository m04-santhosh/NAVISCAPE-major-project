"""
Road Hazard Router
FastAPI routes to create, list, and resolve user road hazard reports.
"""

import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.road_hazard import RoadHazard
from ..models.user import User
from ..schemas.road_hazard import HazardReportCreate, HazardReportResponse

router = APIRouter(prefix="/api/hazards", tags=["Road Hazards"])


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on the Earth in kilometers."""
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


@router.post("", response_model=HazardReportResponse, status_code=status.HTTP_201_CREATED)
async def create_hazard_report(
    payload: HazardReportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a new road hazard report.
    Only authenticated users are allowed, and coordinates, type, and severity are validated.
    """
    new_hazard = RoadHazard(
        user_id=current_user.id,
        hazard_type=payload.hazard_type,
        severity=payload.severity,
        latitude=payload.latitude,
        longitude=payload.longitude,
        description=payload.description,
        status="Active",
    )
    db.add(new_hazard)
    db.commit()
    db.refresh(new_hazard)
    return new_hazard


@router.get("", response_model=List[HazardReportResponse])
async def list_active_hazards(
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: float = 10.0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves active hazards.
    If latitude and longitude are provided, filters hazards to within the specified radius_km.
    Otherwise, returns all active hazards.
    """
    query = db.query(RoadHazard).filter(RoadHazard.status == "Active")

    if latitude is not None and longitude is not None:
        # Simple bounding box pre-filter for performance
        delta_lat = radius_km / 111.0
        lat_rad = math.radians(latitude)
        cos_lat = math.cos(lat_rad)
        delta_lng = radius_km / (111.0 * cos_lat) if cos_lat > 0 else radius_km / 111.0

        min_lat = latitude - delta_lat
        max_lat = latitude + delta_lat
        min_lng = longitude - delta_lng
        max_lng = longitude + delta_lng

        hazards = query.filter(
            RoadHazard.latitude.between(min_lat, max_lat),
            RoadHazard.longitude.between(min_lng, max_lng),
        ).all()

        # Exact distance filtering
        results = [
            h
            for h in hazards
            if haversine_distance(latitude, longitude, h.latitude, h.longitude) <= radius_km
        ]
        return results

    return query.limit(200).all()


@router.put("/{hazard_id}/resolve", response_model=HazardReportResponse)
async def resolve_hazard_report(
    hazard_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deactivates/resolves a hazard report.
    Only the user who reported the hazard is allowed to resolve it.
    """
    hazard = db.query(RoadHazard).filter(RoadHazard.id == hazard_id).first()
    if not hazard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hazard report not found",
        )

    if hazard.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to resolve this hazard report",
        )

    hazard.status = "Resolved"
    db.commit()
    db.refresh(hazard)
    return hazard
