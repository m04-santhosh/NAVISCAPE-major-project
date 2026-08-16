"""
NAVISCAPE Women Safety — Police Station Service
Handles parsing, idempotent importing, and verification of Karnataka Police Station KML datasets.
"""

import os
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List
from collections import Counter
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models.police_station import PoliceStation

logger = logging.getLogger("naviscape.police_service")


def _resolve_kml_path(kml_path: Optional[str] = None) -> str:
    """Resolve default or custom path to police_station.kml."""
    if kml_path and os.path.exists(kml_path):
        return os.path.abspath(kml_path)

    # Base dir: backend root
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_path = os.path.join(base_dir, "data", "police_station.kml")
    if os.path.exists(default_path):
        return default_path

    # Fallback search
    alt_path = os.path.join(os.path.dirname(base_dir), "backend", "data", "police_station.kml")
    if os.path.exists(alt_path):
        return alt_path

    return default_path


def import_police_stations_from_kml(
    db: Session,
    kml_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Idempotent importer for Karnataka police stations from KGIS KML dataset.
    
    Fields:
    - OBJECTID -> object_id
    - DepartmentCode -> department_code
    - POL_STAName -> station_name
    - KGISPOL_STAID -> kgis_pol_sta_id
    - KGISCode -> kgis_code
    - KGISPSCode -> kgis_ps_code
    - KGISVillageID -> kgis_village_id
    - coordinates -> (longitude, latitude) [KML format: lng,lat,alt]
    
    Idempotence: Uses object_id and department_code as stable uniqueness keys.
    Co-located stations sharing coordinates are preserved as distinct records.
    """
    resolved_path = _resolve_kml_path(kml_path)
    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"Police station KML file not found at: {resolved_path}")

    tree = ET.parse(resolved_path)
    root = tree.getroot()
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    placemarks = root.findall('.//kml:Placemark', ns)
    if not placemarks:
        placemarks = root.findall('.//{http://www.opengis.net/kml/2.2}Placemark')

    total_records = len(placemarks)
    inserted = 0
    updated = 0
    skipped = 0
    failed = 0
    failure_details = []

    # Map existing records by object_id for fast lookup
    existing_records = {ps.object_id: ps for ps in db.query(PoliceStation).all()}

    for idx, pm in enumerate(placemarks):
        try:
            # 1. Parse SimpleData tags
            data = {}
            for sd in pm.findall('.//kml:SimpleData', ns):
                name = sd.attrib.get('name')
                val = sd.text
                data[name] = val

            # 2. Parse Point coordinates (KML: lng,lat[,alt])
            coord_elem = pm.find('.//kml:Point/kml:coordinates', ns)
            if coord_elem is None:
                coord_elem = pm.find('.//{http://www.opengis.net/kml/2.2}coordinates')

            if coord_elem is None or not coord_elem.text:
                raise ValueError("Missing Point/coordinates element in placemark")

            parts = [p.strip() for p in coord_elem.text.strip().split(',') if p.strip()]
            if len(parts) < 2:
                raise ValueError(f"Malformed coordinates string: '{coord_elem.text}'")

            lng = float(parts[0])
            lat = float(parts[1])

            # 3. Validate mandatory fields
            raw_obj_id = data.get("OBJECTID")
            if not raw_obj_id:
                raise ValueError("Missing OBJECTID")
            object_id = int(float(raw_obj_id))

            dept_code = data.get("DepartmentCode")
            if not dept_code or not str(dept_code).strip():
                raise ValueError(f"Missing DepartmentCode for OBJECTID {object_id}")
            dept_code = str(dept_code).strip()

            station_name = data.get("POL_STAName")
            if not station_name or not str(station_name).strip():
                raise ValueError(f"Missing POL_STAName for OBJECTID {object_id}")
            station_name = str(station_name).strip()

            # Optional fields
            kgis_pol_sta_id = int(float(data["KGISPOL_STAID"])) if data.get("KGISPOL_STAID") else None
            kgis_code = str(data["KGISCode"]).strip() if data.get("KGISCode") else None
            kgis_ps_code = str(data["KGISPSCode"]).strip() if data.get("KGISPSCode") else None
            kgis_village_id = float(data["KGISVillageID"]) if data.get("KGISVillageID") else None

            # 4. Upsert check
            existing = existing_records.get(object_id)
            if existing:
                # Check if fields changed
                changed = (
                    existing.department_code != dept_code or
                    existing.station_name != station_name or
                    existing.kgis_pol_sta_id != kgis_pol_sta_id or
                    existing.kgis_code != kgis_code or
                    existing.kgis_ps_code != kgis_ps_code or
                    existing.kgis_village_id != kgis_village_id or
                    abs(existing.latitude - lat) > 1e-7 or
                    abs(existing.longitude - lng) > 1e-7
                )
                if changed:
                    existing.department_code = dept_code
                    existing.station_name = station_name
                    existing.kgis_pol_sta_id = kgis_pol_sta_id
                    existing.kgis_code = kgis_code
                    existing.kgis_ps_code = kgis_ps_code
                    existing.kgis_village_id = kgis_village_id
                    existing.latitude = lat
                    existing.longitude = lng
                    updated += 1
                else:
                    skipped += 1
            else:
                new_ps = PoliceStation(
                    object_id=object_id,
                    department_code=dept_code,
                    station_name=station_name,
                    kgis_pol_sta_id=kgis_pol_sta_id,
                    kgis_code=kgis_code,
                    kgis_ps_code=kgis_ps_code,
                    kgis_village_id=kgis_village_id,
                    latitude=lat,
                    longitude=lng,
                )
                db.add(new_ps)
                existing_records[object_id] = new_ps
                inserted += 1

        except Exception as e:
            failed += 1
            logger.warning(f"Failed to import police station at index {idx}: {e}")
            failure_details.append({"index": idx, "error": str(e)})

    db.commit()

    return {
        "total_records": total_records,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "duplicates": skipped,  # idempotent duplicate/existing matches
        "failure_details": failure_details,
        "source": resolved_path,
    }


def verify_police_stations_db(db: Session) -> Dict[str, Any]:
    """
    Read-only audit and verification of the police_stations table.
    Checks counts, geographic bounds, attribute completeness, and co-location integrity.
    """
    stations = db.query(PoliceStation).all()
    total_count = len(stations)

    if total_count == 0:
        return {
            "total_stations": 0,
            "unique_object_ids": 0,
            "unique_department_codes": 0,
            "missing_names": 0,
            "missing_coordinates": 0,
            "min_latitude": None,
            "max_latitude": None,
            "min_longitude": None,
            "max_longitude": None,
            "co_located_groups": 0,
            "co_located_stations_total": 0,
            "data_quality": "EMPTY",
        }

    object_ids = [s.object_id for s in stations]
    dept_codes = [s.department_code for s in stations]
    missing_names = sum(1 for s in stations if not s.station_name or not s.station_name.strip())
    missing_coords = sum(1 for s in stations if s.latitude is None or s.longitude is None)

    lats = [s.latitude for s in stations if s.latitude is not None]
    lngs = [s.longitude for s in stations if s.longitude is not None]

    # Co-located coordinates check
    coord_pairs = [(round(s.latitude, 6), round(s.longitude, 6)) for s in stations if s.latitude and s.longitude]
    coord_counts = Counter(coord_pairs)
    co_located = {k: v for k, v in coord_counts.items() if v > 1}

    return {
        "total_stations": total_count,
        "unique_object_ids": len(set(object_ids)),
        "unique_department_codes": len(set(dept_codes)),
        "missing_names": missing_names,
        "missing_coordinates": missing_coords,
        "min_latitude": min(lats) if lats else None,
        "max_latitude": max(lats) if lats else None,
        "min_longitude": min(lngs) if lngs else None,
        "max_longitude": max(lngs) if lngs else None,
        "co_located_groups": len(co_located),
        "co_located_stations_total": sum(co_located.values()),
        "data_quality": "GOOD" if (total_count == 921 and missing_names == 0 and missing_coords == 0) else "NEEDS_CLEANING",
    }


# ─────────────────────────────────────────────────────────────────────────────
# WS-2: Haversine Distance & Nearest Police Station Intelligence
# ─────────────────────────────────────────────────────────────────────────────

import math


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on the earth in kilometers
    using the Haversine formula (Mean Earth radius R = 6371.0088 km).
    """
    R = 6371.0088  # Mean Earth radius in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def find_nearest_police_station(
    db: Session,
    latitude: float,
    longitude: float,
    radius_km: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Finds the mathematically nearest police station to the given coordinates.
    Sorts deterministically by (distance_km, station_name, id).
    If radius_km is specified, returns None if no station is within that radius.
    """
    if not (-90.0 <= latitude <= 90.0):
        raise ValueError(f"Invalid latitude: {latitude}. Must be between -90 and +90 degrees.")
    if not (-180.0 <= longitude <= 180.0):
        raise ValueError(f"Invalid longitude: {longitude}. Must be between -180 and +180 degrees.")

    query = db.query(PoliceStation)

    # Optional bounding box pre-filter for optimization when radius_km is provided
    if radius_km is not None and radius_km > 0:
        lat_delta = radius_km / 110.574
        cos_lat = math.cos(math.radians(latitude))
        lng_delta = radius_km / (111.320 * max(0.01, abs(cos_lat)))
        query = query.filter(
            PoliceStation.latitude.between(latitude - lat_delta, latitude + lat_delta),
            PoliceStation.longitude.between(longitude - lng_delta, longitude + lng_delta),
        )

    stations = query.all()
    if not stations:
        return None

    # Calculate exact Haversine distance for each candidate
    evaluated = []
    for s in stations:
        d = haversine_distance_km(latitude, longitude, s.latitude, s.longitude)
        if radius_km is None or d <= radius_km:
            evaluated.append((d, s.station_name, s.id, s))

    if not evaluated:
        return None

    # Deterministic sort: distance ASC, then station_name ASC, then id ASC
    evaluated.sort(key=lambda x: (x[0], x[1], x[2]))
    min_dist, _, _, nearest_station = evaluated[0]

    return {
        "station": {
            "id": nearest_station.id,
            "station_name": nearest_station.station_name,
            "latitude": nearest_station.latitude,
            "longitude": nearest_station.longitude,
            "object_id": nearest_station.object_id,
            "department_code": nearest_station.department_code,
            "kgis_pol_sta_id": nearest_station.kgis_pol_sta_id,
            "kgis_code": nearest_station.kgis_code,
            "kgis_ps_code": nearest_station.kgis_ps_code,
        },
        "distance_km": round(min_dist, 3),
        "distance_m": round(min_dist * 1000.0, 1),
    }


def get_police_stations(
    db: Session,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Returns list of police stations, optionally filtered by geographic proximity.
    """
    if lat is not None and not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and +90 degrees.")
    if lng is not None and not (-180.0 <= lng <= 180.0):
        raise ValueError(f"Invalid longitude: {lng}. Must be between -180 and +180 degrees.")

    query = db.query(PoliceStation)

    if lat is not None and lng is not None and radius_km is not None and radius_km > 0:
        lat_delta = radius_km / 110.574
        cos_lat = math.cos(math.radians(lat))
        lng_delta = radius_km / (111.320 * max(0.01, abs(cos_lat)))
        query = query.filter(
            PoliceStation.latitude.between(lat - lat_delta, lat + lat_delta),
            PoliceStation.longitude.between(lng - lng_delta, lng + lng_delta),
        )
        stations = query.all()
        results = []
        for s in stations:
            d = haversine_distance_km(lat, lng, s.latitude, s.longitude)
            if d <= radius_km:
                item = s.to_dict()
                item["distance_km"] = round(d, 3)
                results.append((d, item))
        results.sort(key=lambda x: (x[0], x[1]["station_name"], x[1]["id"]))
        return [r[1] for r in results]
    else:
        stations = query.order_by(PoliceStation.id.asc()).all()
        return [s.to_dict() for s in stations]

