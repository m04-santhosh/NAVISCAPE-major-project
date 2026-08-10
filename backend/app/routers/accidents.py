"""
Accidents Router
API endpoints for query, spatial bounds, clustering, heatmaps, and statistics
on the Karnataka accident dataset.
"""

from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from ..database import get_db
from ..models.accident import AccidentData
from ..schemas.accident import (
    AccidentRecordResponse,
    HeatmapPoint,
    AccidentCluster,
    AccidentStatsResponse,
)

router = APIRouter(prefix="/api/accidents", tags=["Accidents"])

# Severity weight mapping for risk/intensity calculations
SEVERITY_WEIGHTS = {
    "Fatal": 1.0,
    "Grievous Injury": 0.75,
    "Simple Injury": 0.5,
    "Damage Only": 0.25,
}

SEVERITY_SCORE = {
    "Fatal": 5,
    "Grievous Injury": 4,
    "Simple Injury": 3,
    "Damage Only": 2,
}


@router.get("", response_model=List[AccidentRecordResponse])
async def get_accidents(
    district: Optional[str] = Query(None, description="Filter by district name"),
    year: Optional[int] = Query(None, description="Filter by year"),
    severity: Optional[str] = Query(None, description="Filter by severity e.g. Fatal"),
    limit: int = Query(100, ge=1, le=2000, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
):
    """Retrieve filtered accident records with pagination."""
    query = db.query(AccidentData).filter(
        AccidentData.latitude.isnot(None),
        AccidentData.longitude.isnot(None)
    )

    if district:
        query = query.filter(func.lower(AccidentData.district) == district.lower())
    if year:
        query = query.filter(AccidentData.year == year)
    if severity:
        query = query.filter(func.lower(AccidentData.severity) == severity.lower())

    records = query.order_by(AccidentData.id.asc()).offset(offset).limit(limit).all()
    return records


@router.get("/bounds", response_model=List[AccidentRecordResponse])
async def get_accidents_in_bounds(
    min_lat: float = Query(..., description="Minimum latitude"),
    max_lat: float = Query(..., description="Maximum latitude"),
    min_lng: float = Query(..., description="Minimum longitude"),
    max_lng: float = Query(..., description="Maximum longitude"),
    limit: int = Query(500, ge=1, le=5000, description="Max points to return"),
    db: Session = Depends(get_db),
):
    """Get accident records within a geographic bounding box."""
    query = db.query(AccidentData).filter(
        AccidentData.latitude.between(min_lat, max_lat),
        AccidentData.longitude.between(min_lng, max_lng)
    )
    return query.limit(limit).all()


@router.get("/heatmap", response_model=List[HeatmapPoint])
async def get_accident_heatmap(
    district: Optional[str] = Query(None, description="Filter heatmap by district"),
    limit: int = Query(3000, ge=100, le=10000, description="Max points for heatmap"),
    db: Session = Depends(get_db),
):
    """Get weighted heatmap data points for map visualization across Karnataka."""
    query = db.query(
        AccidentData.latitude,
        AccidentData.longitude,
        AccidentData.severity,
        AccidentData.district
    ).filter(
        AccidentData.latitude.isnot(None),
        AccidentData.longitude.isnot(None)
    )

    if district:
        query = query.filter(func.lower(AccidentData.district) == district.lower())

    # Limit to reasonable points for fluid Leaflet rendering
    rows = query.limit(limit).all()

    heatmap_points = []
    for r in rows:
        weight = SEVERITY_WEIGHTS.get(r.severity, 0.4)
        heatmap_points.append(
            HeatmapPoint(
                lat=r.latitude,
                lng=r.longitude,
                intensity=weight,
                severity_weight=weight,
                district=r.district,
                severity=r.severity
            )
        )
    return heatmap_points


@router.get("/clusters", response_model=List[AccidentCluster])
async def get_accident_clusters(
    district: Optional[str] = Query(None, description="Filter clusters by district"),
    db: Session = Depends(get_db),
):
    """
    Get grid-based accident clusters with aggregated risk statistics across Karnataka/districts.
    Groups points by 0.05 degree spatial grid resolution (~5km).
    """
    query = db.query(
        AccidentData.latitude,
        AccidentData.longitude,
        AccidentData.severity,
        AccidentData.main_cause,
        AccidentData.district,
        AccidentData.accident_road
    ).filter(
        AccidentData.latitude.isnot(None),
        AccidentData.longitude.isnot(None)
    )

    if district:
        query = query.filter(func.lower(AccidentData.district) == district.lower())
    else:
        # Default to top accident-dense districts/areas if no district specified to keep response snappy
        query = query.filter(AccidentData.district.in_([
            "Bengaluru City", "Bengaluru Dist", "Tumakuru", "Belagavi Dist", "Mysuru City"
        ]))

    rows = query.limit(8000).all()

    grid_clusters: Dict[str, dict] = {}
    GRID_SIZE = 0.05  # ~5km grid cells

    for r in rows:
        lat_grid = round(r.latitude / GRID_SIZE) * GRID_SIZE
        lng_grid = round(r.longitude / GRID_SIZE) * GRID_SIZE
        key = f"{lat_grid:.2f}_{lng_grid:.2f}"

        if key not in grid_clusters:
            grid_clusters[key] = {
                "lats": [],
                "lngs": [],
                "district": r.district or "Unknown",
                "severities": {},
                "causes": {},
                "samples": [],
            }

        c = grid_clusters[key]
        c["lats"].append(r.latitude)
        c["lngs"].append(r.longitude)
        sev = r.severity or "Unknown"
        c["severities"][sev] = c["severities"].get(sev, 0) + 1
        cause = r.main_cause or "Human Error"
        c["causes"][cause] = c["causes"].get(cause, 0) + 1

        if len(c["samples"]) < 3:
            c["samples"].append({
                "lat": r.latitude,
                "lng": r.longitude,
                "severity": r.severity,
                "road": r.accident_road
            })

    result_clusters = []
    cluster_id = 1
    for key, data in grid_clusters.items():
        if len(data["lats"]) < 5:  # Only return clusters with at least 5 accidents
            continue

        center_lat = sum(data["lats"]) / len(data["lats"])
        center_lng = sum(data["lngs"]) / len(data["lngs"])
        sorted_causes = sorted(data["causes"].items(), key=lambda x: x[1], reverse=True)
        top_causes = [c[0] for c in sorted_causes[:3]]

        result_clusters.append(
            AccidentCluster(
                cluster_id=cluster_id,
                center_lat=round(center_lat, 6),
                center_lng=round(center_lng, 6),
                point_count=len(data["lats"]),
                district=data["district"],
                severity_summary=data["severities"],
                top_causes=top_causes,
                sample_points=data["samples"]
            )
        )
        cluster_id += 1

    result_clusters.sort(key=lambda x: x.point_count, reverse=True)
    return result_clusters[:100]


@router.get("/stats", response_model=AccidentStatsResponse)
async def get_accident_stats(db: Session = Depends(get_db)):
    """Get aggregated statistics from the Karnataka accident dataset."""
    total_records = db.query(AccidentData).count()
    coords_count = db.query(AccidentData).filter(
        AccidentData.latitude.isnot(None),
        AccidentData.longitude.isnot(None)
    ).count()

    districts_count = db.query(func.count(func.distinct(AccidentData.district))).scalar() or 0

    top_dist_rows = db.query(
        AccidentData.district,
        func.count(AccidentData.id).label("count")
    ).group_by(AccidentData.district).order_by(desc("count")).limit(10).all()

    top_districts = [{"district": r[0] or "Unknown", "count": r[1]} for r in top_dist_rows]

    sev_rows = db.query(
        AccidentData.severity,
        func.count(AccidentData.id).label("count")
    ).group_by(AccidentData.severity).all()

    severity_breakdown = { (r[0] or "Unknown"): r[1] for r in sev_rows }

    year_rows = db.query(
        AccidentData.year,
        func.count(AccidentData.id).label("count")
    ).group_by(AccidentData.year).order_by(AccidentData.year.asc()).all()

    yearly_trend = [{"year": r[0], "count": r[1]} for r in year_rows if r[0] is not None]

    cause_rows = db.query(
        AccidentData.main_cause,
        func.count(AccidentData.id).label("count")
    ).group_by(AccidentData.main_cause).order_by(desc("count")).limit(8).all()

    top_causes = [{"cause": r[0] or "Unknown", "count": r[1]} for r in cause_rows]

    return AccidentStatsResponse(
        total_records=total_records,
        records_with_coordinates=coords_count,
        districts_count=districts_count,
        top_districts=top_districts,
        severity_breakdown=severity_breakdown,
        yearly_trend=yearly_trend,
        top_causes=top_causes
    )
