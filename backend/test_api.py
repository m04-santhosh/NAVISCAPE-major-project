"""
Integration tests for NAVISCAPE Backend API Endpoints including Accident Data Module.
"""

from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_accidents_stats_endpoint():
    response = client.get("/api/accidents/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_records" in data
    assert "records_with_coordinates" in data
    assert "districts_count" in data
    assert data["total_records"] > 0
    assert data["records_with_coordinates"] > 0


def test_accidents_list_endpoint():
    response = client.get("/api/accidents?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    record = data[0]
    assert "latitude" in record
    assert "longitude" in record
    assert "district" in record


def test_accidents_heatmap_endpoint():
    response = client.get("/api/accidents/heatmap?limit=100")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    point = data[0]
    assert "lat" in point
    assert "lng" in point
    assert "intensity" in point



def test_accidents_clusters_endpoint():
    response = client.get("/api/accidents/clusters")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        cluster = data[0]
        assert "center_lat" in cluster
        assert "center_lng" in cluster
        assert "point_count" in cluster


def test_accidents_bounds_endpoint():
    # Bounding box covering Bangalore region
    response = client.get("/api/accidents/bounds?min_lat=12.5&max_lat=13.5&min_lng=77.0&max_lng=78.0&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_route_evaluation_endpoint():
    payload = {
        "route_type": "safest",
        "waypoints": [
            [12.9716, 77.5946],
            [12.9591, 77.7010],
            [12.9170, 77.6230]
        ]
    }
    response = client.post("/api/navigation/evaluate-route", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "empirical_safety_score" in data
    assert "total_accidents_nearby" in data
    assert "fatal_accidents_nearby" in data
    assert "hotspots" in data
    assert 0 <= data["empirical_safety_score"] <= 100


def test_risk_prediction_endpoint():
    payload = {
        "latitude": 12.9170,
        "longitude": 77.6230,
        "hour": 9,
        "weather": "rain"
    }
    response = client.post("/api/predict/risk", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "risk_score" in data
    assert "risk_level" in data
    assert "factors" in data
    assert len(data["factors"]) > 0


def test_traffic_predict_endpoint():
    payload = {
        "junction_id": 1,
        "hours_ahead": 3
    }
    response = client.post("/api/predict/traffic", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["junction_id"] == 1
    assert len(data["predictions"]) == 3


def test_navigate_endpoint():
    payload = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "dest_lat": 12.9170,
        "dest_lng": 77.6230,
        "source_name": "MG Road",
        "dest_name": "Silk Board",
        "route_type": "balanced",
        "distance_km": 10.5,
        "duration_min": 25.0,
        "safety_score": 85.0
    }
    response = client.post("/api/navigate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Route saved"


if __name__ == "__main__":
    tests = [
        ("Root Endpoint", test_root_endpoint),
        ("Health Check Endpoint", test_health_check),
        ("Accidents Stats Endpoint", test_accidents_stats_endpoint),
        ("Accidents List Endpoint", test_accidents_list_endpoint),
        ("Accidents Heatmap Endpoint", test_accidents_heatmap_endpoint),
        ("Accidents Clusters Endpoint", test_accidents_clusters_endpoint),
        ("Accidents Bounds Endpoint", test_accidents_bounds_endpoint),
        ("Route Evaluation Endpoint", test_route_evaluation_endpoint),
        ("Risk Prediction Endpoint", test_risk_prediction_endpoint),
        ("Traffic Predict Endpoint", test_traffic_predict_endpoint),
        ("Navigate Save Endpoint", test_navigate_endpoint),
    ]
    print(f"Running NAVISCAPE Backend API Test Suite ({len(tests)} integration tests)...")
    for name, test_func in tests:
        test_func()
        print(f"[PASS] {name}")
    print(f"\nALL {len(tests)} BACKEND INTEGRATION TESTS PASSED SUCCESSFULLY!")


