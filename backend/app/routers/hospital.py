"""
NAVISCAPE Hospital Module — Hospital Router
Read-only endpoints for map-ready Karnataka hospital directory and nearest-hospital intelligence.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..services.hospital_service import get_map_ready_hospitals, find_nearest_hospital

router = APIRouter(prefix="/api/hospitals", tags=["Hospitals"])


@router.get("", response_model=List[Dict[str, Any]])
async def list_hospitals(
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Optional latitude for proximity filtering"),
    lng: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Optional longitude for proximity filtering"),
    latitude: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Alias for lat"),
    longitude: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Alias for lng"),
    radius_km: Optional[float] = Query(None, gt=0.0, description="Optional search radius in kilometers"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    WS-2: Returns the directory of verified, map-ready Karnataka hospitals.
    Only hospitals with valid coordinates inside Karnataka bounds are returned.
    Supports optional geographic radius filtering.
    """
    query_lat = lat if lat is not None else latitude
    query_lng = lng if lng is not None else longitude

    try:
        hospitals = get_map_ready_hospitals(db, lat=query_lat, lng=query_lng, radius_km=radius_km)
        return hospitals
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to retrieve hospitals.")


@router.get("/nearest")
async def get_nearest_hospital(
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="User or query point latitude"),
    lng: Optional[float] = Query(None, ge=-180.0, le=180.0, description="User or query point longitude"),
    latitude: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Alias for lat"),
    longitude: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Alias for lng"),
    radius_km: Optional[float] = Query(None, gt=0.0, description="Optional maximum search radius in kilometers"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    WS-2: Finds the mathematically nearest map-ready Karnataka hospital to the given coordinates.
    Calculates exact Haversine distance.
    Returns 404 if no map-ready hospital exists within the requested radius.
    """
    query_lat = lat if lat is not None else latitude
    query_lng = lng if lng is not None else longitude

    if query_lat is None or query_lng is None:
        raise HTTPException(
            status_code=400,
            detail="Missing required coordinate parameters: 'lat' (or 'latitude') and 'lng' (or 'longitude') are required."
        )

    try:
        nearest = find_nearest_hospital(db, latitude=query_lat, longitude=query_lng, radius_km=radius_km)
        if not nearest:
            raise HTTPException(
                status_code=404,
                detail="No map-ready hospital found within the requested radius."
            )
        return nearest
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to calculate nearest hospital.")
