import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.firebase import get_firestore_db

db = get_firestore_db()
if not db:
    print("Firestore DB client not available")
    sys.exit(1)

collections = [
    "users",
    "emergency_profiles",
    "trusted_contacts",
    "emergency_events",
    "route_history",
    "road_hazards",
    "police_stations",
    "hospital_facilities",
    "accident_data",
    "traffic_data",
    "traffic_hourly"
]

print("=" * 60)
print("CURRENT FIRESTORE COLLECTION COUNTS")
print("=" * 60)

for col in collections:
    if col == "accident_data":
        try:
            res = db.collection(col).count().get()
            count = res[0][0].value
        except Exception:
            count = len(db.collection(col).limit(50000).get())
    else:
        count = len(db.collection(col).get())
    print(f"{col:<25}: {count:,}")

print("=" * 60)
