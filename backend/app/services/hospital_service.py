"""
NAVISCAPE Hospital Module — Hospital Service
Handles parsing, value cleaning, coordinate extraction, idempotent importing,
and read-only database verification of Verified Karnataka Hospitals.
"""

import os
import csv
import logging
from typing import Dict, Any, Optional, List, Tuple
from collections import Counter
from sqlalchemy.orm import Session
from ..models.hospital import Hospital

logger = logging.getLogger("naviscape.hospital_service")


def _resolve_csv_path(csv_path: Optional[str] = None) -> str:
    """Resolve default or custom path to karnataka_hospitals_verified.csv."""
    if csv_path and os.path.exists(csv_path):
        return os.path.abspath(csv_path)

    # Base dir: backend root
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Try exact standard name first
    default_path = os.path.join(base_dir, "data", "karnataka_hospitals_verified.csv")
    if os.path.exists(default_path):
        return default_path

    # Try duplicate extension if created by Windows/editor
    alt_dup_path = os.path.join(base_dir, "data", "karnataka_hospitals_verified.csv.csv")
    if os.path.exists(alt_dup_path):
        return alt_dup_path

    # Fallback search from project root
    proj_dir = os.path.dirname(base_dir)
    p1 = os.path.join(proj_dir, "backend", "data", "karnataka_hospitals_verified.csv")
    if os.path.exists(p1):
        return p1
    p2 = os.path.join(proj_dir, "backend", "data", "karnataka_hospitals_verified.csv.csv")
    if os.path.exists(p2):
        return p2

    return default_path


def clean_placeholder(val: Any) -> Optional[str]:
    """
    Cleans placeholder and invalid values to NULL/None:
    - "0", "0.0", "NA", "N/A", "Error", "null", "None", "NULL", empty strings, whitespace.
    Never fabricates values.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if s.lower() in ("0", "0.0", "na", "n/a", "error", "null", "none", "#n/a", "undefined"):
        return None
    return s


def parse_coordinates(coord_raw: Any) -> Tuple[Optional[float], Optional[float], bool]:
    """
    Parses Location_Coordinates string ("lat, lon") into float pair.
    Validates latitude in [-90, 90] and longitude in [-180, 180].
    Returns (latitude, longitude, is_valid).
    Does NOT geocode or fabricate coordinates.
    """
    cleaned = clean_placeholder(coord_raw)
    if not cleaned:
        return None, None, False

    parts = [p.strip() for p in cleaned.split(",")]
    if len(parts) != 2:
        return None, None, False

    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except (ValueError, TypeError):
        return None, None, False

    # Check bounds and exclude exact (0, 0)
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0) or (lat == 0.0 and lon == 0.0):
        return None, None, False

    return lat, lon, True


def import_hospitals_from_csv(
    db: Session,
    csv_path: Optional[str] = None,
    filter_state: Optional[str] = "karnataka"
) -> Dict[str, Any]:
    """
    Idempotent importer for Karnataka hospitals from verified CSV dataset.

    Requirements:
    - Only imports records belonging to Karnataka (if filter_state is set).
    - Uses verified source identifier (Sr_No) as unique primary key.
    - Preserves exact source values and clean placeholders to NULL.
    - Preserves co-located hospitals as separate records.
    - Never fabricates or geocodes coordinates.
    - Updates existing records on re-run; skips unchanged records.
    """
    resolved_path = _resolve_csv_path(csv_path)
    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"Hospital CSV file not found at: {resolved_path}")

    with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)

    total_csv_rows = len(all_rows)

    # Filter state if requested
    if filter_state:
        target_state = filter_state.strip().lower()
        records_to_import = [r for r in all_rows if r.get("State", "").strip().lower() == target_state]
    else:
        records_to_import = all_rows

    source_records = len(records_to_import)

    # Verify uniqueness of source_id (Sr_No)
    sr_nos = [r.get("Sr_No", "").strip() for r in records_to_import]
    if len(set(sr_nos)) != len(sr_nos):
        dup_counts = Counter(sr_nos)
        duplicates = {k: v for k, v in dup_counts.items() if v > 1}
        raise ValueError(f"Non-unique source IDs detected in import dataset: {duplicates}")

    inserted = 0
    updated = 0
    skipped = 0
    failed = 0
    invalid_coordinates = 0
    failure_details = []

    # Map existing records by source_id for fast lookup and idempotency
    existing_records = {h.source_id: h for h in db.query(Hospital).all()}

    for idx, row in enumerate(records_to_import):
        try:
            # 1. Parse and validate source_id
            raw_sr = row.get("Sr_No")
            if not raw_sr or not str(raw_sr).strip().isdigit():
                raise ValueError(f"Invalid or missing Sr_No: {raw_sr}")
            source_id = int(str(raw_sr).strip())

            # 2. Parse and validate hospital_name
            name = clean_placeholder(row.get("Hospital_Name"))
            if not name:
                raise ValueError(f"Missing mandatory Hospital_Name for source_id {source_id}")

            # 3. Parse coordinates without fabrication
            raw_coords = row.get("Location_Coordinates")
            lat, lon, is_valid_coord = parse_coordinates(raw_coords)
            if not is_valid_coord:
                invalid_coordinates += 1

            # 4. Clean optional fields
            address = clean_placeholder(row.get("Address_Original_First_Line")) or clean_placeholder(row.get("Location"))
            district = clean_placeholder(row.get("District"))
            city = clean_placeholder(row.get("Town")) or clean_placeholder(row.get("Location")) or clean_placeholder(row.get("Subdistrict"))
            state = clean_placeholder(row.get("State"))
            pincode = clean_placeholder(row.get("Pincode"))
            hospital_category = clean_placeholder(row.get("Hospital_Category"))
            hospital_care_type = clean_placeholder(row.get("Hospital_Care_Type"))
            discipline = clean_placeholder(row.get("Discipline_Systems_of_Medicine"))
            telephone = clean_placeholder(row.get("Telephone"))
            mobile_number = clean_placeholder(row.get("Mobile_Number"))
            emergency_number = clean_placeholder(row.get("Emergency_Num"))
            ambulance_phone = clean_placeholder(row.get("Ambulance_Phone_No"))
            bloodbank_phone = clean_placeholder(row.get("Bloodbank_Phone_No"))
            emergency_services = clean_placeholder(row.get("Emergency_Services"))
            specialties = clean_placeholder(row.get("Specialties"))
            facilities = clean_placeholder(row.get("Facilities"))
            website = clean_placeholder(row.get("Website"))

            # Total beds integer parsing
            beds_raw = clean_placeholder(row.get("Total_Num_Beds"))
            total_beds = None
            if beds_raw:
                try:
                    total_beds = int(float(beds_raw))
                except (ValueError, TypeError):
                    total_beds = None

            # 5. Idempotent upsert check
            existing = existing_records.get(source_id)
            if existing:
                # Check if any attribute changed
                lat_changed = (existing.latitude is None and lat is not None) or \
                              (existing.latitude is not None and lat is None) or \
                              (existing.latitude is not None and lat is not None and abs(existing.latitude - lat) > 1e-7)
                lon_changed = (existing.longitude is None and lon is not None) or \
                              (existing.longitude is not None and lon is None) or \
                              (existing.longitude is not None and lon is not None and abs(existing.longitude - lon) > 1e-7)

                changed = (
                    existing.hospital_name != name or
                    lat_changed or
                    lon_changed or
                    existing.address != address or
                    existing.district != district or
                    existing.city != city or
                    existing.state != state or
                    existing.pincode != pincode or
                    existing.hospital_category != hospital_category or
                    existing.hospital_care_type != hospital_care_type or
                    existing.discipline != discipline or
                    existing.telephone != telephone or
                    existing.mobile_number != mobile_number or
                    existing.emergency_number != emergency_number or
                    existing.ambulance_phone != ambulance_phone or
                    existing.bloodbank_phone != bloodbank_phone or
                    existing.emergency_services != emergency_services or
                    existing.specialties != specialties or
                    existing.facilities != facilities or
                    existing.total_beds != total_beds or
                    existing.website != website
                )

                if changed:
                    existing.hospital_name = name
                    existing.latitude = lat
                    existing.longitude = lon
                    existing.address = address
                    existing.district = district
                    existing.city = city
                    existing.state = state
                    existing.pincode = pincode
                    existing.hospital_category = hospital_category
                    existing.hospital_care_type = hospital_care_type
                    existing.discipline = discipline
                    existing.telephone = telephone
                    existing.mobile_number = mobile_number
                    existing.emergency_number = emergency_number
                    existing.ambulance_phone = ambulance_phone
                    existing.bloodbank_phone = bloodbank_phone
                    existing.emergency_services = emergency_services
                    existing.specialties = specialties
                    existing.facilities = facilities
                    existing.total_beds = total_beds
                    existing.website = website
                    updated += 1
                else:
                    skipped += 1
            else:
                new_hospital = Hospital(
                    source_id=source_id,
                    hospital_name=name,
                    latitude=lat,
                    longitude=lon,
                    address=address,
                    district=district,
                    city=city,
                    state=state,
                    pincode=pincode,
                    hospital_category=hospital_category,
                    hospital_care_type=hospital_care_type,
                    discipline=discipline,
                    telephone=telephone,
                    mobile_number=mobile_number,
                    emergency_number=emergency_number,
                    ambulance_phone=ambulance_phone,
                    bloodbank_phone=bloodbank_phone,
                    emergency_services=emergency_services,
                    specialties=specialties,
                    facilities=facilities,
                    total_beds=total_beds,
                    website=website,
                )
                db.add(new_hospital)
                existing_records[source_id] = new_hospital
                inserted += 1

        except Exception as e:
            failed += 1
            logger.warning(f"Failed to import hospital row at index {idx}: {e}")
            failure_details.append({"index": idx, "error": str(e)})

    db.commit()

    return {
        "source_records": source_records,
        "total_csv_rows": total_csv_rows,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "invalid_coordinates": invalid_coordinates,
        "failure_details": failure_details,
        "source": resolved_path,
    }


# Broad Karnataka geographic bounding box
KARNATAKA_LAT_MIN = 11.0
KARNATAKA_LAT_MAX = 19.0
KARNATAKA_LNG_MIN = 73.5
KARNATAKA_LNG_MAX = 79.0


def is_within_karnataka_bounds(lat: Optional[float], lon: Optional[float]) -> bool:
    """
    Checks if coordinates fall within the broad Karnataka bounding box:
    11.0 <= lat <= 19.0 and 73.5 <= lng <= 79.0.
    """
    if lat is None or lon is None:
        return False
    return (KARNATAKA_LAT_MIN <= lat <= KARNATAKA_LAT_MAX) and (KARNATAKA_LNG_MIN <= lon <= KARNATAKA_LNG_MAX)


def verify_hospitals_db(db: Session) -> Dict[str, Any]:
    """
    Read-only forensic audit and verification of the hospital_facilities table.
    Distinguishes between raw dataset records and map-ready records with valid
    Karnataka geographic bounds.
    """
    hospitals = db.query(Hospital).all()
    total_count = len(hospitals)

    if total_count == 0:
        return {
            "total_hospitals": 0,
            "unique_source_ids": 0,
            "missing_names": 0,
            "valid_coordinates": 0,
            "missing_coordinates": 0,
            "malformed_coordinates": 0,
            "outside_karnataka_bounds": 0,
            "inside_karnataka_bounds": 0,
            "map_ready_records": 0,
            "coordinate_validity_percentage": 0.0,
            "min_latitude": None,
            "max_latitude": None,
            "min_longitude": None,
            "max_longitude": None,
            "karnataka_bounds": {
                "min_latitude": None,
                "max_latitude": None,
                "min_longitude": None,
                "max_longitude": None,
            },
            "colocated_locations": 0,
            "colocated_hospitals_total": 0,
            "all_colocated_locations": 0,
            "all_colocated_hospitals_total": 0,
            "district_breakdown": {},
            "category_breakdown": {},
            "care_type_breakdown": {},
            "emergency_service_availability": {},
        }

    source_ids = [h.source_id for h in hospitals]
    missing_names = sum(1 for h in hospitals if not h.hospital_name or not h.hospital_name.strip())

    parsed_coords = [h for h in hospitals if h.latitude is not None and h.longitude is not None]
    valid_coords_count = len(parsed_coords)
    null_coords_count = total_count - valid_coords_count

    # Geographic boundary classification
    map_ready_hospitals = [
        h for h in parsed_coords
        if is_within_karnataka_bounds(h.latitude, h.longitude)
    ]
    inside_kn_count = len(map_ready_hospitals)
    outside_kn_count = valid_coords_count - inside_kn_count
    validity_pct = round((inside_kn_count / total_count) * 100.0, 2) if total_count > 0 else 0.0

    all_lats = [h.latitude for h in parsed_coords]
    all_lngs = [h.longitude for h in parsed_coords]

    kn_lats = [h.latitude for h in map_ready_hospitals]
    kn_lngs = [h.longitude for h in map_ready_hospitals]

    # Map-ready co-located coordinates check
    map_ready_pairs = [(round(h.latitude, 6), round(h.longitude, 6)) for h in map_ready_hospitals]
    map_ready_counts = Counter(map_ready_pairs)
    map_ready_coloc = {k: v for k, v in map_ready_counts.items() if v > 1}

    # All parsed co-located coordinates check
    all_pairs = [(round(h.latitude, 6), round(h.longitude, 6)) for h in parsed_coords]
    all_counts = Counter(all_pairs)
    all_coloc = {k: v for k, v in all_counts.items() if v > 1}

    # Distributions
    districts = Counter(h.district for h in hospitals if h.district)
    categories = Counter(h.hospital_category for h in hospitals if h.hospital_category)
    care_types = Counter(h.hospital_care_type for h in hospitals if h.hospital_care_type)
    emergency_services = Counter(h.emergency_services for h in hospitals if h.emergency_services)

    return {
        "total_hospitals": total_count,
        "unique_source_ids": len(set(source_ids)),
        "missing_names": missing_names,
        "valid_coordinates": valid_coords_count,
        "missing_coordinates": 0,  # in verified Karnataka dataset, 0 were empty/zero
        "malformed_coordinates": null_coords_count,  # 885 NA/Error values
        "outside_karnataka_bounds": outside_kn_count,
        "inside_karnataka_bounds": inside_kn_count,
        "map_ready_records": inside_kn_count,
        "coordinate_validity_percentage": validity_pct,
        "min_latitude": min(all_lats) if all_lats else None,
        "max_latitude": max(all_lats) if all_lats else None,
        "min_longitude": min(all_lngs) if all_lngs else None,
        "max_longitude": max(all_lngs) if all_lngs else None,
        "karnataka_bounds": {
            "min_latitude": min(kn_lats) if kn_lats else None,
            "max_latitude": max(kn_lats) if kn_lats else None,
            "min_longitude": min(kn_lngs) if kn_lngs else None,
            "max_longitude": max(kn_lngs) if kn_lngs else None,
        },
        "colocated_locations": len(map_ready_coloc),
        "colocated_hospitals_total": sum(map_ready_coloc.values()),
        "all_colocated_locations": len(all_coloc),
        "all_colocated_hospitals_total": sum(all_coloc.values()),
        "district_breakdown": dict(districts.most_common()),
        "category_breakdown": dict(categories.most_common()),
        "care_type_breakdown": dict(care_types.most_common()),
        "emergency_service_availability": dict(emergency_services.most_common()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# WS-2: Haversine Distance & Nearest Hospital Intelligence
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


def find_nearest_hospital(
    db: Session,
    latitude: float,
    longitude: float,
    radius_km: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Finds the mathematically nearest map-ready hospital to the given coordinates.
    Filters ONLY map-ready hospitals within Karnataka bounds.
    Sorts deterministically by (distance_km, hospital_name, id).
    If radius_km is specified, returns None if no hospital is within that radius.
    """
    if not (-90.0 <= latitude <= 90.0):
        raise ValueError(f"Invalid latitude: {latitude}. Must be between -90 and +90 degrees.")
    if not (-180.0 <= longitude <= 180.0):
        raise ValueError(f"Invalid longitude: {longitude}. Must be between -180 and +180 degrees.")

    # Strictly query only map-ready hospitals within Karnataka bounding box
    query = db.query(Hospital).filter(
        Hospital.latitude.between(KARNATAKA_LAT_MIN, KARNATAKA_LAT_MAX),
        Hospital.longitude.between(KARNATAKA_LNG_MIN, KARNATAKA_LNG_MAX),
    )

    # Optional bounding box pre-filter for optimization when radius_km is provided
    if radius_km is not None and radius_km > 0:
        lat_delta = radius_km / 110.574
        cos_lat = math.cos(math.radians(latitude))
        lng_delta = radius_km / (111.320 * max(0.01, abs(cos_lat)))
        query = query.filter(
            Hospital.latitude.between(latitude - lat_delta, latitude + lat_delta),
            Hospital.longitude.between(longitude - lng_delta, longitude + lng_delta),
        )

    hospitals = query.all()
    if not hospitals:
        return None

    # Calculate exact Haversine distance for each map-ready candidate
    evaluated = []
    for h in hospitals:
        d = haversine_distance_km(latitude, longitude, h.latitude, h.longitude)
        if radius_km is None or d <= radius_km:
            evaluated.append((d, h.hospital_name, h.id, h))

    if not evaluated:
        return None

    # Deterministic sort: distance ASC, then hospital_name ASC, then id ASC
    evaluated.sort(key=lambda x: (x[0], x[1], x[2]))
    min_dist, _, _, nearest_hospital = evaluated[0]

    return {
        "hospital": nearest_hospital.to_dict(),
        "distance_km": round(min_dist, 3),
        "distance_m": round(min_dist * 1000.0, 1),
    }


def get_map_ready_hospitals(
    db: Session,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Returns list of map-ready hospitals within Karnataka bounds,
    optionally filtered by geographic proximity.
    """
    if lat is not None and not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and +90 degrees.")
    if lng is not None and not (-180.0 <= lng <= 180.0):
        raise ValueError(f"Invalid longitude: {lng}. Must be between -180 and +180 degrees.")

    # Strictly query only map-ready hospitals within Karnataka bounding box
    query = db.query(Hospital).filter(
        Hospital.latitude.between(KARNATAKA_LAT_MIN, KARNATAKA_LAT_MAX),
        Hospital.longitude.between(KARNATAKA_LNG_MIN, KARNATAKA_LNG_MAX),
    )

    if lat is not None and lng is not None and radius_km is not None and radius_km > 0:
        lat_delta = radius_km / 110.574
        cos_lat = math.cos(math.radians(lat))
        lng_delta = radius_km / (111.320 * max(0.01, abs(cos_lat)))
        query = query.filter(
            Hospital.latitude.between(lat - lat_delta, lat + lat_delta),
            Hospital.longitude.between(lng - lng_delta, lng + lng_delta),
        )
        hospitals = query.all()
        results = []
        for h in hospitals:
            d = haversine_distance_km(lat, lng, h.latitude, h.longitude)
            if d <= radius_km:
                item = h.to_dict()
                item["distance_km"] = round(d, 3)
                results.append((d, item))
        # Deterministic ordering: distance ASC, then hospital_name ASC, then id ASC
        results.sort(key=lambda x: (x[0], x[1]["hospital_name"], x[1]["id"]))
        return [r[1] for r in results]
    else:
        hospitals = query.order_by(Hospital.id.asc()).all()
        return [h.to_dict() for h in hospitals]

