import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.firebase import get_firebase_app, get_firestore_db
from migrate_to_firestore import get_sqlite_conn, commit_batch

app = get_firebase_app()
db = get_firestore_db()
conn = get_sqlite_conn()
cursor = conn.cursor()

BATCH_SIZE = 250

# 10. TRAFFIC DATA
print("Migrating traffic_data...", flush=True)
cursor.execute("SELECT * FROM traffic_data")
t_rows = cursor.fetchall()
print(f"Source traffic_data rows: {len(t_rows)}", flush=True)
ops = []
for r in t_rows:
    doc_id = f"traffic_{r['id']}"
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
        s, f = commit_batch(db, ops)
        print(f"  traffic_data chunk committed: {s} ok, {f} fail", flush=True)
        ops = []
if ops:
    s, f = commit_batch(db, ops)
    print(f"  traffic_data chunk committed: {s} ok, {f} fail", flush=True)

# 11. TRAFFIC HOURLY
print("Migrating traffic_hourly...", flush=True)
cursor.execute("SELECT * FROM traffic_hourly")
th_rows = cursor.fetchall()
print(f"Source traffic_hourly rows: {len(th_rows)}", flush=True)
ops = []
for r in th_rows:
    doc_id = f"hourly_{r['id']}"
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
    s, f = commit_batch(db, ops)
    print(f"  traffic_hourly chunk committed: {s} ok, {f} fail", flush=True)

print("Traffic migration completed successfully!", flush=True)
