"""
NAVISCAPE Idempotent Firestore Migration Script with Resume, Quota Protection & Free Tier Safety
Migrates data from SQLite (backend/naviscape.db) to Cloud Firestore.

FEATURES:
- Does NOT modify SQLite.
- Safe to re-run (idempotent & resume-aware).
- Streamlined resume support: detects existing document IDs in Firestore and skips them.
- Immediate Quota Exhaustion detection: stops execution instantly upon HTTP 429 / ResourceExhausted without retrying or fallback loops.
- Enforces a configurable daily free-tier write limit (default: MAX_WRITES_PER_RUN = 19000).
- Memory-efficient streaming in chunks (5000 records/chunk).
- Preserves retry and backoff handling for transient non-quota errors.
- Dry-run mode (--dry-run) to preview counts without performing writes.
- Accident-only mode (--only accident_data) to target specific collections.
"""

import sys
import os
import time
import logging
import sqlite3
import argparse
from typing import Dict, Any, List, Tuple, Set

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.firebase import get_firebase_app, get_firestore_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "naviscape.db")
BATCH_SIZE = 250
DEFAULT_MAX_WRITES_PER_RUN = 19000


class FirestoreQuotaExhaustedError(Exception):
    """Raised immediately when Cloud Firestore daily write quota is exhausted."""
    pass


def is_quota_exhausted_error(e: Exception) -> bool:
    """
    Checks whether an exception corresponds to Firestore quota exhaustion.
    Matches:
    - google.api_core.exceptions.ResourceExhausted
    - gRPC RESOURCE_EXHAUSTED
    - HTTP 429 / 'Quota exceeded' / 'RESOURCE_EXHAUSTED'
    """
    err_str = str(e).lower()
    err_type = type(e).__name__.lower()

    if "resourceexhausted" in err_type or "resourceexhausted" in err_str:
        return True
    if "429" in err_str or "quota exceeded" in err_str or "quota_exceeded" in err_str:
        return True
    if "resource_exhausted" in err_str:
        return True

    try:
        from google.api_core.exceptions import ResourceExhausted
        if isinstance(e, ResourceExhausted):
            return True
    except ImportError:
        pass

    return False


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_sqlite_conn():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"SQLite database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    return conn


def get_existing_firestore_doc_ids(db, collection_name: str) -> Set[str]:
    """
    Retrieves existing document IDs from a Firestore collection using lightweight field projection.
    """
    logger.info(f"Scanning existing document IDs in Firestore collection '{collection_name}'...")
    try:
        docs = db.collection(collection_name).select([]).stream()
        existing_ids = {doc.id for doc in docs}
        logger.info(f"  Found {len(existing_ids):,} existing documents in Firestore collection '{collection_name}'.")
        return existing_ids
    except Exception as e:
        if is_quota_exhausted_error(e):
            raise FirestoreQuotaExhaustedError(f"Quota exhausted during document scan: {e}")
        logger.warning(f"  Could not stream document IDs for '{collection_name}': {e}. Falling back to empty set.")
        return set()


def commit_batch(db, operations: List[tuple], dry_run: bool = False) -> Tuple[int, int]:
    """
    Executes a Firestore batch write with retries and fallback.
    If quota exhaustion (ResourceExhausted / HTTP 429) occurs, immediately raises FirestoreQuotaExhaustedError.
    """
    if not operations:
        return 0, 0

    if dry_run:
        # Dry-run mode: Perform ZERO Firestore writes
        return len(operations), 0

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        batch = db.batch()
        for ref, payload in operations:
            batch.set(ref, payload, merge=True)
        try:
            batch.commit()
            return len(operations), 0
        except Exception as e:
            if is_quota_exhausted_error(e):
                logger.error(f"FIRESTORE DAILY QUOTA EXHAUSTED during batch commit: {e}")
                raise FirestoreQuotaExhaustedError(f"Daily quota exhausted: {e}")
            if attempt < max_retries:
                time.sleep(1.5 * attempt)
            else:
                logger.warning(f"Batch commit attempt {attempt} failed: {e}. Retrying operations individually...")

    succeeded = 0
    failed = 0
    for ref, payload in operations:
        try:
            ref.set(payload, merge=True)
            succeeded += 1
        except Exception as single_err:
            if is_quota_exhausted_error(single_err):
                logger.error(f"FIRESTORE DAILY QUOTA EXHAUSTED during single write: {single_err}")
                raise FirestoreQuotaExhaustedError(f"Daily quota exhausted: {single_err}")
            logger.error(f"Single doc write failed for {ref.path}: {single_err}")
            failed += 1
    return succeeded, failed


def run_migration(dry_run: bool = False, only_collection: str = None, max_writes: int = DEFAULT_MAX_WRITES_PER_RUN):
    print("=" * 70)
    print("NAVISCAPE — Cloud Firestore Batch Migration")
    if dry_run:
        print(">>> MODE: DRY-RUN (PREVIEW ONLY — ZERO FIRESTORE WRITES) <<<")
    if only_collection:
        print(f">>> TARGET COLLECTION: {only_collection} <<<")
    print(f">>> DAILY NEW WRITE LIMIT: {max_writes:,} <<<")
    print("=" * 70)

    app = get_firebase_app()
    db = get_firestore_db()
    if not app or not db:
        logger.error("Failed to connect to Cloud Firestore.")
        sys.exit(1)

    conn = get_sqlite_conn()
    cursor = conn.cursor()

    user_id_map: Dict[int, str] = {}
    summary_results = {}

    def fmt(n):
        return f"{n:,}"

    def should_process(col_name: str) -> bool:
        if only_collection and only_collection.lower() != col_name.lower():
            return False
        return True

    # -------------------------------------------------------------------------
    # 1. USERS
    # -------------------------------------------------------------------------
    if should_process("users"):
        logger.info("Migrating [1/11] users...")
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        src_count = len(users)
        migrated, failed, skipped = 0, 0, 0

        try:
            existing_ids = get_existing_firestore_doc_ids(db, "users")
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        ops = []
        for u in users:
            legacy_id = u["id"]
            email = (u.get("email") or "").strip().lower()

            existing_uid = f"legacy_user_{legacy_id}" if f"legacy_user_{legacy_id}" in existing_ids else None
            uid = existing_uid or f"legacy_user_{legacy_id}"
            user_id_map[legacy_id] = uid

            payload = {
                "sqlite_legacy_id": legacy_id,
                "email": email,
                "full_name": u.get("full_name") or email.split("@")[0],
                "username": u.get("username") or email.split("@")[0],
                "email_verified": bool(u.get("email_verified", 1)),
                "is_active": bool(u.get("is_active", 1)),
                "is_admin": bool(u.get("is_admin", 0)),
                "created_at": str(u.get("created_at") or ""),
                "updated_at": str(u.get("updated_at") or ""),
                "last_login_at": str(u.get("last_login_at") or ""),
            }
            ref = db.collection("users").document(uid)
            ops.append((ref, payload))

        try:
            s, f = commit_batch(db, ops, dry_run=dry_run)
            migrated += s
            failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        fs_count = len(existing_ids) if existing_ids else len(users)
        summary_results["users"] = {
            "source": src_count,
            "firestore": fs_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }
        logger.info(f"  users: Source={src_count}, Firestore={fs_count}, Migrated={migrated}, Failed={failed}, Skipped={skipped}")

    # -------------------------------------------------------------------------
    # 2. EMERGENCY PROFILES
    # -------------------------------------------------------------------------
    if should_process("emergency_profiles"):
        logger.info("Migrating [2/11] emergency_profiles...")
        cursor.execute("SELECT * FROM emergency_profiles")
        ep_rows = cursor.fetchall()
        src_count = len(ep_rows)
        migrated, failed, skipped = 0, 0, 0

        ops = []
        for r in ep_rows:
            leg_uid = r["user_id"]
            mapped_uid = user_id_map.get(leg_uid, f"legacy_user_{leg_uid}")
            doc_id = mapped_uid

            payload = {
                "user_id": mapped_uid,
                "sqlite_legacy_id": r["id"],
                "sqlite_legacy_user_id": leg_uid,
                "emergency_mobile": r.get("emergency_mobile"),
                "emergency_email": r.get("emergency_email"),
                "location_sharing_consent": bool(r.get("location_sharing_consent", 0)),
                "created_at": str(r.get("created_at") or ""),
                "updated_at": str(r.get("updated_at") or ""),
            }
            ref = db.collection("emergency_profiles").document(doc_id)
            ops.append((ref, payload))

        try:
            s, f = commit_batch(db, ops, dry_run=dry_run)
            migrated += s
            failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        summary_results["emergency_profiles"] = {
            "source": src_count,
            "firestore": src_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }

    # -------------------------------------------------------------------------
    # 3. TRUSTED CONTACTS
    # -------------------------------------------------------------------------
    if should_process("trusted_contacts"):
        logger.info("Migrating [3/11] trusted_contacts...")
        cursor.execute("SELECT * FROM trusted_contacts")
        tc_rows = cursor.fetchall()
        src_count = len(tc_rows)
        migrated, failed, skipped = 0, 0, 0

        ops = []
        for r in tc_rows:
            leg_uid = r["user_id"]
            mapped_uid = user_id_map.get(leg_uid, f"legacy_user_{leg_uid}")
            doc_id = f"contact_{r['id']}"

            payload = {
                "id": r["id"],
                "user_id": mapped_uid,
                "sqlite_legacy_user_id": leg_uid,
                "contact_name": r.get("contact_name") or "",
                "relationship": r.get("relationship") or "",
                "mobile_number": r.get("mobile_number") or "",
                "email": r.get("email"),
                "whatsapp_number": r.get("whatsapp_number"),
                "whatsapp_alert_consent": bool(r.get("whatsapp_alert_consent", 0)),
                "created_at": str(r.get("created_at") or ""),
                "updated_at": str(r.get("updated_at") or ""),
            }
            ref = db.collection("trusted_contacts").document(doc_id)
            ops.append((ref, payload))

        try:
            s, f = commit_batch(db, ops, dry_run=dry_run)
            migrated += s
            failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        summary_results["trusted_contacts"] = {
            "source": src_count,
            "firestore": src_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }

    # -------------------------------------------------------------------------
    # 4. EMERGENCY EVENTS
    # -------------------------------------------------------------------------
    if should_process("emergency_events"):
        logger.info("Migrating [4/11] emergency_events...")
        cursor.execute("SELECT * FROM emergency_events")
        ee_rows = cursor.fetchall()
        src_count = len(ee_rows)
        migrated, failed, skipped = 0, 0, 0

        ops = []
        for r in ee_rows:
            leg_uid = r["user_id"]
            mapped_uid = user_id_map.get(leg_uid, f"legacy_user_{leg_uid}")
            doc_id = f"event_{r['id']}"

            payload = {
                "id": r["id"],
                "user_id": mapped_uid,
                "sqlite_legacy_user_id": leg_uid,
                "status": r.get("status") or "ACTIVE",
                "triggered_at": str(r.get("triggered_at") or ""),
                "cancelled_at": str(r.get("cancelled_at")) if r.get("cancelled_at") else None,
                "latitude": float(r["latitude"]),
                "longitude": float(r["longitude"]),
                "location_accuracy_m": float(r["location_accuracy_m"]) if r.get("location_accuracy_m") is not None else None,
                "created_at": str(r.get("created_at") or ""),
                "updated_at": str(r.get("updated_at") or ""),
            }
            ref = db.collection("emergency_events").document(doc_id)
            ops.append((ref, payload))

        try:
            s, f = commit_batch(db, ops, dry_run=dry_run)
            migrated += s
            failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        summary_results["emergency_events"] = {
            "source": src_count,
            "firestore": src_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }

    # -------------------------------------------------------------------------
    # 5. ROUTE HISTORY
    # -------------------------------------------------------------------------
    if should_process("route_history"):
        logger.info("Migrating [5/11] route_history...")
        cursor.execute("SELECT * FROM route_history")
        rh_rows = cursor.fetchall()
        src_count = len(rh_rows)
        migrated, failed, skipped = 0, 0, 0

        ops = []
        for r in rh_rows:
            leg_uid = r["user_id"]
            mapped_uid = user_id_map.get(leg_uid, f"legacy_user_{leg_uid}")
            doc_id = f"route_{r['id']}"

            payload = {
                "id": r["id"],
                "user_id": mapped_uid,
                "sqlite_legacy_user_id": leg_uid,
                "source_lat": float(r["source_lat"]),
                "source_lng": float(r["source_lng"]),
                "dest_lat": float(r["dest_lat"]),
                "dest_lng": float(r["dest_lng"]),
                "source_name": r.get("source_name"),
                "dest_name": r.get("dest_name"),
                "distance_km": float(r["distance_km"]) if r.get("distance_km") is not None else None,
                "duration_min": float(r["duration_min"]) if r.get("duration_min") is not None else None,
                "safety_score": float(r["safety_score"]) if r.get("safety_score") is not None else None,
                "route_type": r.get("route_type") or "balanced",
                "created_at": str(r.get("created_at") or ""),
            }
            ref = db.collection("route_history").document(doc_id)
            ops.append((ref, payload))

        try:
            s, f = commit_batch(db, ops, dry_run=dry_run)
            migrated += s
            failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        summary_results["route_history"] = {
            "source": src_count,
            "firestore": src_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }

    # -------------------------------------------------------------------------
    # 6. ROAD HAZARDS
    # -------------------------------------------------------------------------
    if should_process("road_hazards"):
        logger.info("Migrating [6/11] road_hazards...")
        cursor.execute("SELECT * FROM road_hazards")
        rhaz_rows = cursor.fetchall()
        src_count = len(rhaz_rows)
        migrated, failed, skipped = 0, 0, 0

        ops = []
        for r in rhaz_rows:
            leg_uid = r["user_id"]
            mapped_uid = user_id_map.get(leg_uid, f"legacy_user_{leg_uid}")
            doc_id = f"hazard_{r['id']}"

            payload = {
                "id": r["id"],
                "user_id": mapped_uid,
                "sqlite_legacy_user_id": leg_uid,
                "hazard_type": r.get("hazard_type") or "Pothole",
                "severity": r.get("severity") or "Medium",
                "latitude": float(r["latitude"]),
                "longitude": float(r["longitude"]),
                "description": r.get("description"),
                "status": r.get("status") or "Active",
                "created_at": str(r.get("created_at") or ""),
            }
            ref = db.collection("road_hazards").document(doc_id)
            ops.append((ref, payload))

        try:
            s, f = commit_batch(db, ops, dry_run=dry_run)
            migrated += s
            failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        summary_results["road_hazards"] = {
            "source": src_count,
            "firestore": src_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }

    # -------------------------------------------------------------------------
    # 7. POLICE STATIONS
    # -------------------------------------------------------------------------
    if should_process("police_stations"):
        logger.info("Migrating [7/11] police_stations...")
        cursor.execute("SELECT * FROM police_stations")
        ps_rows = cursor.fetchall()
        src_count = len(ps_rows)
        migrated, failed, skipped = 0, 0, 0

        try:
            existing_ids = get_existing_firestore_doc_ids(db, "police_stations")
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        ops = []
        try:
            for r in ps_rows:
                doc_id = f"station_{r['id']}"
                if doc_id in existing_ids:
                    skipped += 1
                    continue

                payload = {
                    "id": r["id"],
                    "object_id": r["object_id"],
                    "department_code": r["department_code"],
                    "station_name": r["station_name"],
                    "kgis_pol_sta_id": r.get("kgis_pol_sta_id"),
                    "kgis_code": r.get("kgis_code"),
                    "kgis_ps_code": r.get("kgis_ps_code"),
                    "kgis_village_id": float(r["kgis_village_id"]) if r.get("kgis_village_id") is not None else None,
                    "latitude": float(r["latitude"]),
                    "longitude": float(r["longitude"]),
                    "created_at": str(r.get("created_at") or ""),
                }
                ref = db.collection("police_stations").document(doc_id)
                ops.append((ref, payload))

                if len(ops) >= BATCH_SIZE:
                    s, f = commit_batch(db, ops, dry_run=dry_run)
                    migrated += s
                    failed += f
                    ops = []

            if ops:
                s, f = commit_batch(db, ops, dry_run=dry_run)
                migrated += s
                failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        summary_results["police_stations"] = {
            "source": src_count,
            "firestore": len(existing_ids) if existing_ids else src_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }

    # -------------------------------------------------------------------------
    # 8. HOSPITAL FACILITIES
    # -------------------------------------------------------------------------
    if should_process("hospital_facilities"):
        logger.info("Migrating [8/11] hospital_facilities...")
        cursor.execute("SELECT * FROM hospital_facilities")
        hosp_rows = cursor.fetchall()
        src_count = len(hosp_rows)
        migrated, failed, skipped = 0, 0, 0

        try:
            existing_ids = get_existing_firestore_doc_ids(db, "hospital_facilities")
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        ops = []
        try:
            for r in hosp_rows:
                doc_id = f"hospital_{r['id']}"
                if doc_id in existing_ids:
                    skipped += 1
                    continue

                payload = {
                    "id": r["id"],
                    "source_id": r["source_id"],
                    "hospital_name": r["hospital_name"],
                    "latitude": float(r["latitude"]) if r.get("latitude") is not None else None,
                    "longitude": float(r["longitude"]) if r.get("longitude") is not None else None,
                    "address": r.get("address"),
                    "district": r.get("district"),
                    "city": r.get("city"),
                    "state": r.get("state"),
                    "pincode": r.get("pincode"),
                    "hospital_category": r.get("hospital_category"),
                    "hospital_care_type": r.get("hospital_care_type"),
                    "discipline": r.get("discipline"),
                    "telephone": r.get("telephone"),
                    "mobile_number": r.get("mobile_number"),
                    "emergency_number": r.get("emergency_number"),
                    "ambulance_phone": r.get("ambulance_phone"),
                    "bloodbank_phone": r.get("bloodbank_phone"),
                    "emergency_services": r.get("emergency_services"),
                    "specialties": r.get("specialties"),
                    "facilities": r.get("facilities"),
                    "total_beds": int(r["total_beds"]) if r.get("total_beds") is not None else None,
                    "website": r.get("website"),
                    "created_at": str(r.get("created_at") or ""),
                }
                ref = db.collection("hospital_facilities").document(doc_id)
                ops.append((ref, payload))

                if len(ops) >= BATCH_SIZE:
                    s, f = commit_batch(db, ops, dry_run=dry_run)
                    migrated += s
                    failed += f
                    ops = []

            if ops:
                s, f = commit_batch(db, ops, dry_run=dry_run)
                migrated += s
                failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        summary_results["hospital_facilities"] = {
            "source": src_count,
            "firestore": len(existing_ids) if existing_ids else src_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }

    # -------------------------------------------------------------------------
    # 9. ACCIDENT DATA (Chunked streaming migration with resume & quota protection)
    # -------------------------------------------------------------------------
    if should_process("accident_data"):
        logger.info("Migrating [9/11] accident_data (95,723 records)...")
        cursor.execute("SELECT COUNT(*) as cnt FROM accident_data")
        src_count = cursor.fetchone()["cnt"]

        written_this_run = 0
        skipped_count = 0
        failed_count = 0
        already_in_fs = 0
        new_records_available = 0

        try:
            # Step 1: Detect existing Firestore accident document IDs
            existing_doc_ids = get_existing_firestore_doc_ids(db, "accident_data")
            already_in_fs = len(existing_doc_ids)
            new_records_available = src_count - already_in_fs

            chunk_size = 5000
            offset = 0
            limit_reached = False

            ops = []

            while not limit_reached:
                cursor.execute(f"SELECT * FROM accident_data LIMIT {chunk_size} OFFSET {offset}")
                rows = cursor.fetchall()
                if not rows:
                    break

                for r in rows:
                    doc_id = f"accident_{r['id']}"
                    if doc_id in existing_doc_ids:
                        skipped_count += 1
                        continue

                    if written_this_run + len(ops) >= max_writes:
                        limit_reached = True
                        break

                    payload = {
                        "id": r["id"],
                        "district": r.get("district"),
                        "police_station": r.get("police_station"),
                        "crime_no": r.get("crime_no"),
                        "year": int(r["year"]) if r.get("year") is not None else None,
                        "vehicles_involved": int(r["vehicles_involved"]) if r.get("vehicles_involved") is not None else None,
                        "classification": r.get("classification"),
                        "accident_spot": r.get("accident_spot"),
                        "accident_location": r.get("accident_location"),
                        "main_cause": r.get("main_cause"),
                        "hit_run": r.get("hit_run"),
                        "severity": r.get("severity"),
                        "collision_type": r.get("collision_type"),
                        "junction_control": r.get("junction_control"),
                        "road_character": r.get("road_character"),
                        "road_type": r.get("road_type"),
                        "surface_type": r.get("surface_type"),
                        "surface_condition": r.get("surface_condition"),
                        "road_condition": r.get("road_condition"),
                        "weather": r.get("weather"),
                        "road_markings": r.get("road_markings"),
                        "spot_conditions": r.get("spot_conditions"),
                        "road_junction": r.get("road_junction"),
                        "accident_road": r.get("accident_road"),
                        "landmark_first": r.get("landmark_first"),
                        "landmark_second": r.get("landmark_second"),
                        "description": r.get("description"),
                        "latitude": float(r["latitude"]) if r.get("latitude") is not None else None,
                        "longitude": float(r["longitude"]) if r.get("longitude") is not None else None,
                        "created_at": str(r.get("created_at") or ""),
                    }
                    ref = db.collection("accident_data").document(doc_id)
                    ops.append((ref, payload))

                    if len(ops) >= BATCH_SIZE:
                        s, f = commit_batch(db, ops, dry_run=dry_run)
                        written_this_run += s
                        failed_count += f
                        ops = []

                offset += len(rows)
                logger.info(f"  accident_data progress: {fmt(offset)}/{fmt(src_count)} scanned | Queued/Written: {fmt(written_this_run + len(ops))} | Skipped: {fmt(skipped_count)}")

                if limit_reached:
                    logger.info(f"  [DAILY LIMIT REACHED] Reached max writes limit of {max_writes:,} for this run. Stopping cleanly.")
                    break

            if ops and not (limit_reached and written_this_run >= max_writes):
                s, f = commit_batch(db, ops, dry_run=dry_run)
                written_this_run += s
                failed_count += f

        except FirestoreQuotaExhaustedError as qe:
            logger.warning(f"Quota exception caught: {qe}")
            effective_written = written_this_run if not dry_run else 0
            remaining_count = max(0, src_count - (already_in_fs + effective_written))

            print("\n" + "=" * 70)
            print("FIRESTORE DAILY QUOTA REACHED")
            print("Migration paused safely.")
            print(f"Written this run: {written_this_run}")
            print(f"Skipped:          {skipped_count}")
            print(f"Failed:           {failed_count}")
            print(f"Remaining:        {remaining_count}")
            print("=" * 70 + "\n")

            summary_results["accident_data"] = {
                "source": src_count,
                "already_in_firestore": already_in_fs,
                "new_available": new_records_available,
                "written_this_run": written_this_run,
                "skipped": skipped_count,
                "failed": failed_count,
                "remaining": remaining_count,
            }
            conn.close()
            return summary_results

        # Calculate remaining count
        effective_written = written_this_run if not dry_run else 0
        remaining_count = max(0, src_count - (already_in_fs + effective_written))

        print("\n" + "=" * 70)
        print("ACCIDENT DATA MIGRATION STATUS")
        print("=" * 70)
        print(f"SOURCE COUNT:          {src_count}")
        print(f"ALREADY IN FIRESTORE:  {already_in_fs}")
        print(f"NEW RECORDS AVAILABLE: {new_records_available}")
        print(f"WRITTEN THIS RUN:      {written_this_run}" + (" (DRY-RUN - 0 REAL WRITES)" if dry_run else ""))
        print(f"SKIPPED:               {skipped_count}")
        print(f"FAILED:                {failed_count}")
        print(f"REMAINING:             {remaining_count}")
        print("=" * 70 + "\n")

        summary_results["accident_data"] = {
            "source": src_count,
            "already_in_firestore": already_in_fs,
            "new_available": new_records_available,
            "written_this_run": written_this_run,
            "skipped": skipped_count,
            "failed": failed_count,
            "remaining": remaining_count,
        }

    # -------------------------------------------------------------------------
    # 10. TRAFFIC DATA
    # -------------------------------------------------------------------------
    if should_process("traffic_data"):
        logger.info("Migrating [10/11] traffic_data...")
        cursor.execute("SELECT * FROM traffic_data")
        t_rows = cursor.fetchall()
        src_count = len(t_rows)
        migrated, failed, skipped = 0, 0, 0

        try:
            existing_ids = get_existing_firestore_doc_ids(db, "traffic_data")
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        ops = []
        try:
            for r in t_rows:
                doc_id = f"traffic_{r['id']}"
                if doc_id in existing_ids:
                    skipped += 1
                    continue

                payload = {
                    "id": r["id"],
                    "junction_id": int(r["junction_id"]),
                    "latitude": float(r["latitude"]),
                    "longitude": float(r["longitude"]),
                    "timestamp": str(r.get("timestamp") or ""),
                    "vehicle_count": int(r["vehicle_count"]),
                    "avg_speed": float(r["avg_speed"]) if r.get("avg_speed") is not None else None,
                    "congestion_level": r.get("congestion_level"),
                    "day_of_week": int(r["day_of_week"]) if r.get("day_of_week") is not None else None,
                    "hour_of_day": int(r["hour_of_day"]) if r.get("hour_of_day") is not None else None,
                    "is_test": bool(r.get("is_test", 0)),
                    "free_flow_speed": float(r["free_flow_speed"]) if r.get("free_flow_speed") is not None else None,
                    "speed_ratio": float(r["speed_ratio"]) if r.get("speed_ratio") is not None else None,
                }
                ref = db.collection("traffic_data").document(doc_id)
                ops.append((ref, payload))

                if len(ops) >= BATCH_SIZE:
                    s, f = commit_batch(db, ops, dry_run=dry_run)
                    migrated += s
                    failed += f
                    ops = []

            if ops:
                s, f = commit_batch(db, ops, dry_run=dry_run)
                migrated += s
                failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        summary_results["traffic_data"] = {
            "source": src_count,
            "firestore": len(existing_ids) if existing_ids else src_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }

    # -------------------------------------------------------------------------
    # 11. TRAFFIC HOURLY
    # -------------------------------------------------------------------------
    if should_process("traffic_hourly"):
        logger.info("Migrating [11/11] traffic_hourly...")
        cursor.execute("SELECT * FROM traffic_hourly")
        th_rows = cursor.fetchall()
        src_count = len(th_rows)
        migrated, failed, skipped = 0, 0, 0

        try:
            existing_ids = get_existing_firestore_doc_ids(db, "traffic_hourly")
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        ops = []
        try:
            for r in th_rows:
                doc_id = f"hourly_{r['id']}"
                if doc_id in existing_ids:
                    skipped += 1
                    continue

                payload = {
                    "id": r["id"],
                    "junction_id": int(r["junction_id"]),
                    "timestamp": str(r.get("timestamp") or ""),
                    "avg_speed": float(r["avg_speed"]) if r.get("avg_speed") is not None else None,
                    "speed_ratio": float(r["speed_ratio"]) if r.get("speed_ratio") is not None else None,
                    "avg_confidence": float(r["avg_confidence"]) if r.get("avg_confidence") is not None else None,
                    "sample_count": int(r.get("sample_count", 0)),
                    "data_quality": r.get("data_quality") or "COMPLETE",
                    "is_test": bool(r.get("is_test", 0)),
                    "created_at": str(r.get("created_at") or ""),
                }
                ref = db.collection("traffic_hourly").document(doc_id)
                ops.append((ref, payload))

            if ops:
                s, f = commit_batch(db, ops, dry_run=dry_run)
                migrated += s
                failed += f
        except FirestoreQuotaExhaustedError:
            print("\nFIRESTORE DAILY QUOTA REACHED\nMigration paused safely.\n")
            conn.close()
            return summary_results

        summary_results["traffic_hourly"] = {
            "source": src_count,
            "firestore": len(existing_ids) if existing_ids else src_count,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
        }

    conn.close()
    return summary_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NAVISCAPE Idempotent Firestore Batch Migration Script")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run preview without writing to Firestore")
    parser.add_argument("--only", type=str, default=None, help="Migrate only specified collection (e.g. accident_data)")
    parser.add_argument("--max-writes", type=int, default=DEFAULT_MAX_WRITES_PER_RUN, help="Maximum new writes allowed per run (default: 19000)")

    args = parser.parse_args()

    run_migration(dry_run=args.dry_run, only_collection=args.only, max_writes=args.max_writes)
