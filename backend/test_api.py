"""
Integration tests for NAVISCAPE Backend API Endpoints.
Covers: Auth (Email + PIN + OTP), Accident data module (Phase 2), route safety (Phase 3),
route optimization (Phase 4), and traffic intelligence (Phase 5).
"""

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.otp import OTPRecord, OTPPurpose
from app.middleware.auth import hash_pin
from datetime import datetime, timedelta, timezone

client = TestClient(app)


# ── Global token store for authenticated requests ─────────────────────────────
_auth_headers = {}


def test_auth_signup_flow():
    """Test full Email + OTP + PIN registration flow."""
    test_email = "testuser_auth@gmail.com"

    # Cleanup any pre-existing test records from previous test runs
    db_setup = SessionLocal()
    try:
        user_to_del = db_setup.query(User).filter(User.email == test_email).first()
        if user_to_del:
            db_setup.delete(user_to_del)
            db_setup.commit()
        db_setup.query(OTPRecord).filter(OTPRecord.email == test_email).delete()
        db_setup.commit()
    finally:
        db_setup.close()

    # Step 1: Send OTP
    res1 = client.post("/api/auth/send-signup-otp", json={"email": test_email})
    assert res1.status_code == 200, f"Expected 200, got {res1.status_code}: {res1.json()}"
    assert "verification code has been sent" in res1.json()["message"]

    # Retrieve created OTP hash directly from DB (bypassing email delivery for test)
    db = SessionLocal()
    try:
        otp_rec = db.query(OTPRecord).filter(
            OTPRecord.email == test_email,
            OTPRecord.purpose == OTPPurpose.SIGNUP
        ).order_by(OTPRecord.created_at.desc()).first()
        assert otp_rec is not None

        # Verify invalid OTP is rejected
        res_bad = client.post("/api/auth/verify-signup-otp", json={"email": test_email, "otp": "000000"})
        assert res_bad.status_code == 400

        # Inject known OTP for verification testing
        import hashlib
        known_otp = "123456"
        otp_rec.otp_hash = hashlib.sha256(known_otp.encode()).hexdigest()
        db.commit()

        # Step 2: Verify OTP
        res2 = client.post("/api/auth/verify-signup-otp", json={"email": test_email, "otp": known_otp})
        assert res2.status_code == 200
        token_data = res2.json()
        assert "verification_token" in token_data

        verif_token = token_data["verification_token"]

        # Step 3: Set PIN
        res3 = client.post("/api/auth/set-pin", json={
            "email": test_email,
            "verification_token": verif_token,
            "pin": "654321",
            "confirm_pin": "654321"
        })
        assert res3.status_code == 201
        data = res3.json()
        assert "access_token" in data
        assert data["user"]["email"] == test_email
        assert data["user"]["email_verified"] is True

        # Store token for subsequent authenticated tests
        global _auth_headers
        _auth_headers = {"Authorization": f"Bearer {data['access_token']}"}

    finally:
        db.close()


def test_auth_login_flow():
    """Test Email + PIN login with valid and invalid credentials."""
    test_email = "testuser_auth@gmail.com"

    # Invalid PIN
    res_bad = client.post("/api/auth/login", json={"email": test_email, "pin": "000000"})
    assert res_bad.status_code == 401

    # Valid PIN
    res_good = client.post("/api/auth/login", json={"email": test_email, "pin": "654321"})
    assert res_good.status_code == 200
    data = res_good.json()
    assert "access_token" in data
    assert data["user"]["email"] == test_email


def test_auth_me_endpoint():
    """Test GET /api/auth/me requiring JWT token."""
    # Without header -> 401
    res_unauth = client.get("/api/auth/me")
    assert res_unauth.status_code == 401

    # With header -> 200
    res_auth = client.get("/api/auth/me", headers=_auth_headers)
    assert res_auth.status_code == 200
    assert res_auth.json()["email"] == "testuser_auth@gmail.com"


def test_auth_forgot_pin_flow():
    """Test Forgot PIN OTP request, verification, and reset."""
    test_email = "testuser_auth@gmail.com"

    # Step 1: Send Forgot PIN OTP
    res1 = client.post("/api/auth/forgot-pin/send-otp", json={"email": test_email})
    assert res1.status_code == 200

    # Inject known OTP into DB
    db = SessionLocal()
    try:
        import hashlib
        known_otp = "888888"
        otp_rec = db.query(OTPRecord).filter(
            OTPRecord.email == test_email,
            OTPRecord.purpose == OTPPurpose.FORGOT_PIN
        ).order_by(OTPRecord.created_at.desc()).first()
        assert otp_rec is not None
        otp_rec.otp_hash = hashlib.sha256(known_otp.encode()).hexdigest()
        db.commit()

        # Step 2: Verify Forgot PIN OTP
        res2 = client.post("/api/auth/forgot-pin/verify-otp", json={"email": test_email, "otp": known_otp})
        assert res2.status_code == 200
        token = res2.json()["verification_token"]

        # Step 3: Reset PIN
        res3 = client.post("/api/auth/forgot-pin/reset", json={
            "email": test_email,
            "verification_token": token,
            "new_pin": "112233",
            "confirm_pin": "112233"
        })
        assert res3.status_code == 200

        # Verify old PIN is rejected
        res_old = client.post("/api/auth/login", json={"email": test_email, "pin": "654321"})
        assert res_old.status_code == 401

        # Verify new PIN works
        res_new = client.post("/api/auth/login", json={"email": test_email, "pin": "112233"})
        assert res_new.status_code == 200

    finally:
        db.close()


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
    response = client.post("/api/navigation/evaluate-route", json=payload, headers=_auth_headers)
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
    response = client.post("/api/predict/risk", json=payload, headers=_auth_headers)
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
    response = client.post("/api/predict/traffic", json=payload, headers=_auth_headers)
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
    response = client.post("/api/navigate", json=payload, headers=_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Route saved"


def test_route_optimization_endpoint():
    payload = {
        "routes": [
            {
                "route_id": "shortest",
                "route_type": "shortest",
                "distance_km": 10.2,
                "duration_min": 22.0,
                "waypoints": [[12.9716, 77.5946], [12.9170, 77.6230]]
            },
            {
                "route_id": "safest",
                "route_type": "safest",
                "distance_km": 12.5,
                "duration_min": 27.0,
                "waypoints": [[12.9716, 77.5946], [12.9352, 77.6245], [12.9170, 77.6230]]
            }
        ]
    }
    response = client.post("/api/navigation/optimize-routes", json=payload, headers=_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "routes" in data
    assert len(data["routes"]) == 2
    assert "recommended_route_id" in data
    assert "recommendation_reasons" in data
    assert len(data["recommendation_reasons"]) > 0
    route = data["routes"][0]
    assert "overall_score" in route
    assert "safety_score" in route
    assert "traffic_score" in route
    assert "eta_score" in route
    assert "distance_score" in route
    assert 0 <= route["overall_score"] <= 100
    # Phase 5: verify traffic intelligence fields are present
    assert "traffic_level" in route
    assert "prediction_available" in route
    assert "traffic_source" in route
    assert "prediction_horizon_minutes" in route
    assert route["traffic_level"] in ["Low", "Moderate", "High", "Severe"]


def test_route_traffic_intelligence_endpoint():
    """Phase 5: POST /api/traffic/evaluate-route returns legitimate traffic intelligence."""
    payload = {
        "waypoints": [
            [12.9716, 77.5946],
            [12.9170, 77.6230],
            [12.9591, 77.7010]
        ],
        "distance_km": 12.5,
        "duration_min": 25.0,
        "prediction_horizon_minutes": 30
    }
    response = client.post("/api/traffic/evaluate-route", json=payload, headers=_auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Core structure
    assert "traffic_score" in data
    assert "current_traffic_score" in data
    assert "traffic_level" in data
    assert "traffic_source" in data
    assert "traffic_confidence" in data
    assert "prediction_available" in data
    assert "prediction_horizon_minutes" in data

    # Score validation
    assert 0 < data["traffic_score"] <= 100
    assert 0 < data["current_traffic_score"] <= 100
    assert data["traffic_level"] in ["Low", "Moderate", "High", "Severe"]
    assert isinstance(data["prediction_available"], bool)
    assert data["prediction_horizon_minutes"] == 30
    assert data["traffic_confidence"] >= 0.0


if __name__ == "__main__":
    tests = [
        ("Root Endpoint", test_root_endpoint),
        ("Health Check Endpoint", test_health_check),
        ("Auth Signup Flow (OTP + PIN)", test_auth_signup_flow),
        ("Auth Login Flow (Email + PIN)", test_auth_login_flow),
        ("Auth Me Profile Endpoint (JWT)", test_auth_me_endpoint),
        ("Auth Forgot PIN Flow", test_auth_forgot_pin_flow),
        ("Accidents Stats Endpoint", test_accidents_stats_endpoint),
        ("Accidents List Endpoint", test_accidents_list_endpoint),
        ("Accidents Heatmap Endpoint", test_accidents_heatmap_endpoint),
        ("Accidents Clusters Endpoint", test_accidents_clusters_endpoint),
        ("Accidents Bounds Endpoint", test_accidents_bounds_endpoint),
        ("Route Evaluation Endpoint", test_route_evaluation_endpoint),
        ("Risk Prediction Endpoint", test_risk_prediction_endpoint),
        ("Traffic Predict Endpoint", test_traffic_predict_endpoint),
        ("Navigate Save Endpoint", test_navigate_endpoint),
        ("Route Optimization Endpoint", test_route_optimization_endpoint),
        ("Route Traffic Intelligence Endpoint", test_route_traffic_intelligence_endpoint),
    ]
    print(f"Running NAVISCAPE Backend API Test Suite ({len(tests)} integration tests)...")
    for name, test_func in tests:
        test_func()
        print(f"[PASS] {name}")
    print(f"\nALL {len(tests)} BACKEND INTEGRATION TESTS PASSED SUCCESSFULLY!")
