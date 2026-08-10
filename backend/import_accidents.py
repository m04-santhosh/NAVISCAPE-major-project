"""
Karnataka Accident Data Importer CLI & Utility Module
Parses backend/data/accidents/karnataka_accidents.csv and populates SQLite database.
"""

import sys
import os
import csv
import time
import argparse
from sqlalchemy import text
from app.database import engine, SessionLocal, init_db
from app.models.accident import AccidentData

DATASET_PATH = os.path.join("data", "accidents", "karnataka_accidents.csv")
if not os.path.exists(DATASET_PATH):
    DATASET_PATH = os.path.join("backend", "data", "accidents", "karnataka_accidents.csv")


def parse_float(val):
    if not val:
        return None
    try:
        f = float(val)
        return f if f != 0.0 else None
    except (ValueError, TypeError):
        return None

def parse_int(val):
    if not val:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

def import_accidents(csv_path=None, limit=None, batch_size=2000):
    if not csv_path:
        csv_path = DATASET_PATH

    if not os.path.exists(csv_path):
        print(f"Error: CSV dataset file not found at {csv_path}")
        return 0

    init_db()
    db = SessionLocal()

    start_time = time.time()
    print(f"Starting import from {csv_path}...")

    imported_count = 0
    skipped_count = 0
    batch = []

    try:
        with open(csv_path, mode="r", encoding="latin-1", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lat = parse_float(row.get("Latitude"))
                lng = parse_float(row.get("Longitude"))

                # Strict coordinate validation for Karnataka (Lat ~11.0 to 19.0, Lng ~74.0 to 79.0)
                if not lat or not lng or not (11.0 <= lat <= 19.0) or not (74.0 <= lng <= 79.0):
                    skipped_count += 1
                    continue

                crime_no = row.get("Crime_No")
                if crime_no:
                    crime_no = crime_no.strip()

                record = AccidentData(
                    district=row.get("DISTRICTNAME"),
                    police_station=row.get("UNITNAME"),
                    crime_no=crime_no,
                    year=parse_int(row.get("Year")),
                    vehicles_involved=parse_int(row.get("Noofvehicle_involved")),
                    classification=row.get("Accident_Classification"),
                    accident_spot=row.get("Accident_Spot"),
                    accident_location=row.get("Accident_Location"),
                    main_cause=row.get("Main_Cause"),
                    hit_run=row.get("Hit_Run"),
                    severity=row.get("Severity"),
                    collision_type=row.get("Collision_Type"),
                    junction_control=row.get("Junction_Control"),
                    road_character=row.get("Road_Character"),
                    road_type=row.get("Road_Type"),
                    surface_type=row.get("Surface_Type"),
                    surface_condition=row.get("Surface_Condition"),
                    road_condition=row.get("Road_Condition"),
                    weather=row.get("Weather"),
                    road_markings=row.get("Road_Markings"),
                    spot_conditions=row.get("Spot_Conditions"),
                    road_junction=row.get("RoadJunction"),
                    accident_road=row.get("Accident_Road"),
                    landmark_first=row.get("Landmark_first"),
                    landmark_second=row.get("landmark_second"),
                    description=row.get("Accident_Description"),
                    latitude=lat,
                    longitude=lng,
                )
                batch.append(record)

                if len(batch) >= batch_size:
                    db.bulk_save_objects(batch)
                    db.commit()
                    imported_count += len(batch)
                    batch = []
                    print(f"Imported {imported_count} records...")

                if limit and (imported_count + len(batch)) >= limit:
                    break

            if batch:
                db.bulk_save_objects(batch)
                db.commit()
                imported_count += len(batch)

    except Exception as e:
        db.rollback()
        print(f"Error during import: {e}")
        raise e
    finally:
        db.close()

    elapsed = round(time.time() - start_time, 2)
    print(f"Import complete! {imported_count} records imported, {skipped_count} invalid/missing coordinate rows skipped in {elapsed}s.")
    return imported_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Karnataka Accident CSV dataset into NAVISCAPE SQLite database.")
    parser.add_argument("--csv", type=str, default=DATASET_PATH, help="Path to CSV dataset")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of valid records to import")
    args = parser.parse_args()

    import_accidents(csv_path=args.csv, limit=args.limit)
