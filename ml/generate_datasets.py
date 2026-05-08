"""
NAVISCAPE - Synthetic Dataset Generator
Generates realistic traffic, accident, and road network data for Bangalore.
"""
import csv, os, random
from datetime import datetime, timedelta

random.seed(42)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

JUNCTIONS = {
    1: ("Silk Board Junction", 12.9170, 77.6230),
    2: ("Hebbal Flyover", 13.0358, 77.5970),
    3: ("KR Puram Junction", 13.0012, 77.6960),
    4: ("Marathahalli Bridge", 12.9591, 77.7010),
    5: ("Whitefield Junction", 12.9698, 77.7500),
    6: ("Banashankari Circle", 12.9255, 77.5468),
    7: ("Jayanagar 4th Block", 12.9260, 77.5830),
    8: ("MG Road Metro", 12.9756, 77.6066),
}

def generate_traffic_data():
    print("[1/3] Generating traffic data...")
    filepath = os.path.join(OUTPUT_DIR, "traffic_data.csv")
    fields = ["junction_id","latitude","longitude","timestamp","vehicle_count",
              "avg_speed","congestion_level","day_of_week","hour_of_day"]
    start = datetime(2023, 1, 1)
    rows = []
    for day_offset in range(730):  # 2 years
        dt = start + timedelta(days=day_offset)
        dow = dt.weekday()
        for hour in range(24):
            for jid, (name, lat, lng) in JUNCTIONS.items():
                base = random.randint(60, 180)
                if hour in [8,9,17,18,19]: base = int(base * random.uniform(2.2, 3.2))
                elif hour in [7,10,16,20]: base = int(base * random.uniform(1.5, 2.0))
                elif hour in [0,1,2,3,4,5]: base = int(base * random.uniform(0.08, 0.25))
                if dow >= 5: base = int(base * 0.65)
                if jid == 1: base = int(base * 1.4)
                speed = max(5, 60 - base/10 + random.uniform(-5, 5))
                if base > 400: cl = "critical"
                elif base > 250: cl = "high"
                elif base > 150: cl = "medium"
                else: cl = "low"
                ts = dt.replace(hour=hour, minute=0, second=0)
                rows.append([jid, lat, lng, ts.isoformat(), base, round(speed,1), cl, dow, hour])
    with open(filepath, "w", newline="") as f:
        w = csv.writer(f); w.writerow(fields); w.writerows(rows)
    print(f"   Generated {len(rows)} traffic records -> {filepath}")

def generate_accident_data():
    print("[2/3] Generating accident data...")
    filepath = os.path.join(OUTPUT_DIR, "accident_data.csv")
    fields = ["latitude","longitude","severity","timestamp","weather_condition",
              "road_condition","description","casualties"]
    weathers = ["clear","clear","clear","cloudy","rain","rain","fog","heavy_rain"]
    roads = ["dry","dry","dry","wet","wet","icy","pothole"]
    descs = [
        "Rear-end collision at signal","Two-wheeler skid","Pedestrian hit",
        "Side collision at intersection","Vehicle rollover","Head-on collision",
        "Hit-and-run incident","Multi-vehicle pile-up","Bus-auto collision",
    ]
    hotspots = [(12.917,77.623),(12.934,77.610),(13.001,77.696),(12.970,77.750),
                (12.976,77.607),(13.036,77.597),(12.959,77.701),(12.926,77.547)]
    rows = []
    for _ in range(2000):
        hs = random.choice(hotspots)
        lat = hs[0] + random.uniform(-0.015, 0.015)
        lng = hs[1] + random.uniform(-0.015, 0.015)
        sev = random.choices([1,2,3,4,5], weights=[30,30,20,15,5])[0]
        ts = datetime(2023,1,1) + timedelta(days=random.randint(0,729),
             hours=random.randint(0,23), minutes=random.randint(0,59))
        rows.append([round(lat,6), round(lng,6), sev, ts.isoformat(),
                     random.choice(weathers), random.choice(roads),
                     random.choice(descs), random.randint(0, sev)])
    with open(filepath, "w", newline="") as f:
        w = csv.writer(f); w.writerow(fields); w.writerows(rows)
    print(f"   Generated {len(rows)} accident records -> {filepath}")

def generate_road_network():
    print("[3/3] Generating road network data...")
    filepath = os.path.join(OUTPUT_DIR, "road_network.csv")
    fields = ["node_id","latitude","longitude","name","connected_to","distance_km"]
    nodes = [(jid, lat, lng, name) for jid,(name,lat,lng) in JUNCTIONS.items()]
    rows = []
    for i, (nid, lat, lng, name) in enumerate(nodes):
        connections = random.sample([n[0] for n in nodes if n[0] != nid], min(3, len(nodes)-1))
        for cid in connections:
            cn = next(n for n in nodes if n[0] == cid)
            import math
            dist = 6371*2*math.asin(math.sqrt(
                math.sin(math.radians(cn[1]-lat)/2)**2 +
                math.cos(math.radians(lat))*math.cos(math.radians(cn[1]))*
                math.sin(math.radians(cn[2]-lng)/2)**2
            ))
            rows.append([nid, lat, lng, name, cid, round(dist*random.uniform(1.1,1.4),2)])
    with open(filepath, "w", newline="") as f:
        w = csv.writer(f); w.writerow(fields); w.writerows(rows)
    print(f"   Generated {len(rows)} road network edges -> {filepath}")

if __name__ == "__main__":
    print("="*50)
    print("NAVISCAPE Dataset Generator")
    print("="*50)
    generate_traffic_data()
    generate_accident_data()
    generate_road_network()
    print("\nAll datasets generated successfully!")
