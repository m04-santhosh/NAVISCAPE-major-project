"""
NAVISCAPE Women Safety — Police Station Router
Read-only endpoints for police station directory and nearest-station intelligence.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..services.police_service import get_police_stations, find_nearest_police_station

router = APIRouter(prefix="/api/police-stations", tags=["Police Stations"])


@router.get("", response_model=List[Dict[str, Any]])
async def list_police_stations(
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Optional latitude for proximity filtering"),
    lng: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Optional longitude for proximity filtering"),
    radius_km: Optional[float] = Query(None, gt=0.0, description="Optional search radius in kilometers"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    WS-2: Returns the directory of verified Karnataka police stations.
    Supports optional geographic radius filtering.
    """
    try:
        stations = get_police_stations(db, lat=lat, lng=lng, radius_km=radius_km)
        return stations
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to retrieve police stations.")


@router.get("/nearest")
async def get_nearest_police_station(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="User or query point latitude"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="User or query point longitude"),
    radius_km: Optional[float] = Query(None, gt=0.0, description="Optional maximum search radius in kilometers"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    WS-2: Finds the mathematically nearest verified Karnataka police station to the given coordinates.
    Calculates exact Haversine distance.
    Returns 404 if no station exists within the requested radius.
    """
    try:
        nearest = find_nearest_police_station(db, latitude=latitude, longitude=longitude, radius_km=radius_km)
        if not nearest:
            raise HTTPException(
                status_code=404,
                detail="No police station found within the requested radius."
            )
        return nearest
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to calculate nearest police station.")
