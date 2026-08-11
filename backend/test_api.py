"""
Integration tests for NAVISCAPE Backend API Endpoints.
Covers: Auth (Email + PIN + OTP), Accident data module (Phase 2), route safety (Phase 3),
route optimization (Phase 4), and traffic intelligence (Phase 5).
"""

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app.models.user import User
from app.models.otp import OTPRecord, OTPPurpose
from app.middleware.auth import hash_pin
from datetime import datetime, timedelta, timezone

# Ensure database tables and migrations are initialized
init_db()

client = TestClient(app, raise_server_exceptions=False)


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
            from app.models.road_hazard import RoadHazard
            db_setup.query(RoadHazard).filter(RoadHazard.user_id == user_to_del.id).delete()
            db_setup.commit()
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
    # Verify unauthenticated request is blocked
    response_unauth = client.get("/api/accidents/stats")
    assert response_unauth.status_code == 401
    
    response = client.get("/api/accidents/stats", headers=_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_records" in data
    assert "records_with_coordinates" in data
    assert "districts_count" in data
    assert data["total_records"] > 0
    assert data["records_with_coordinates"] > 0


def test_accidents_list_endpoint():
    # Verify unauthenticated request is blocked
    response_unauth = client.get("/api/accidents?limit=5")
    assert response_unauth.status_code == 401

    response = client.get("/api/accidents?limit=5", headers=_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    record = data[0]
    assert "latitude" in record
    assert "longitude" in record
    assert "district" in record


def test_accidents_heatmap_endpoint():
    # Verify unauthenticated request is blocked
    response_unauth = client.get("/api/accidents/heatmap?limit=100")
    assert response_unauth.status_code == 401

    response = client.get("/api/accidents/heatmap?limit=100", headers=_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    point = data[0]
    assert "lat" in point
    assert "lng" in point
    assert "intensity" in point


def test_accidents_clusters_endpoint():
    # Verify unauthenticated request is blocked
    response_unauth = client.get("/api/accidents/clusters")
    assert response_unauth.status_code == 401

    response = client.get("/api/accidents/clusters", headers=_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        cluster = data[0]
        assert "center_lat" in cluster
        assert "center_lng" in cluster
        assert "point_count" in cluster


def test_accidents_bounds_endpoint():
    # Verify unauthenticated request is blocked
    response_unauth = client.get("/api/accidents/bounds?min_lat=12.5&max_lat=13.5&min_lng=77.0&max_lng=78.0&limit=5")
    assert response_unauth.status_code == 401

    # Bounding box covering Bangalore region
    response = client.get("/api/accidents/bounds?min_lat=12.5&max_lat=13.5&min_lng=77.0&max_lng=78.0&limit=5", headers=_auth_headers)
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


def test_road_hazards_endpoint():
    """Phase 6: Live Road Hazards reporting, fetching, and resolving."""
    # 1. Create a hazard report
    payload = {
        "hazard_type": "Pothole",
        "severity": "High",
        "latitude": 12.9170,
        "longitude": 77.6230,
        "description": "Very large pothole near Silk Board."
    }
    response = client.post("/api/hazards", json=payload, headers=_auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["hazard_type"] == "Pothole"
    assert data["severity"] == "High"
    assert data["status"] == "Active"
    assert "id" in data
    hazard_id = data["id"]

    # 2. Get nearby hazards (active only)
    response = client.get("/api/hazards?latitude=12.9170&longitude=77.6230&radius_km=5.0", headers=_auth_headers)
    assert response.status_code == 200
    nearby = response.json()
    assert len(nearby) > 0
    assert any(h["id"] == hazard_id for h in nearby)

    # 3. Resolve the hazard report
    response = client.put(f"/api/hazards/{hazard_id}/resolve", headers=_auth_headers)
    assert response.status_code == 200
    resolved_data = response.json()
    assert resolved_data["status"] == "Resolved"

    # 4. Verify it is no longer returned in nearby active hazards
    response = client.get("/api/hazards?latitude=12.9170&longitude=77.6230&radius_km=5.0", headers=_auth_headers)
    assert response.status_code == 200
    nearby_after = response.json()
    assert not any(h["id"] == hazard_id for h in nearby_after)


def test_dynamic_hazard_routing_endpoint():
    """Phase 7: Verify that active hazards dynamically update route safety scores, ETA delays, and alternate evaluations."""
    # 1. Post a new active critical hazard on a route waypoint (e.g. at 12.9300, 77.6200)
    payload_active = {
        "hazard_type": "Road blocked",  # Blocked road triggers BOTH safety penalty and ETA delay
        "severity": "Critical",
        "latitude": 12.9300,
        "longitude": 77.6200,
        "description": "Critical road block for dynamic routing test."
    }
    response = client.post("/api/hazards", json=payload_active, headers=_auth_headers)
    assert response.status_code == 201
    active_hazard = response.json()
    active_id = active_hazard["id"]

    # 2. Post a second hazard that is RESOLVED (status=Resolved) to verify it is ignored by routing
    payload_resolved = {
        "hazard_type": "Accident",
        "severity": "High",
        "latitude": 12.9320,
        "longitude": 77.6220,
        "description": "Resolved accident to verify ignore rules."
    }
    response = client.post("/api/hazards", json=payload_resolved, headers=_auth_headers)
    assert response.status_code == 201
    resolved_hazard = response.json()
    resolved_id = resolved_hazard["id"]
    # Mark it resolved
    response_resolve = client.put(f"/api/hazards/{resolved_id}/resolve", headers=_auth_headers)
    assert response_resolve.status_code == 200

    # 3. Call evaluate-route and verify safety penalties and active hazards are returned
    payload_eval = {
        "route_type": "safest",
        "waypoints": [
            [12.9716, 77.5946],
            [12.9300, 77.6200],  # Right on the active hazard
            [12.9320, 77.6220],  # Right on the resolved hazard
            [12.9170, 77.6230]
        ]
    }
    response = client.post("/api/navigation/evaluate-route", json=payload_eval, headers=_auth_headers)
    assert response.status_code == 200
    eval_data = response.json()
    
    # Assertions
    assert eval_data["active_hazards_nearby"] == 1
    # Verify the list contains only the active hazard
    assert len(eval_data["live_hazards"]) == 1
    assert eval_data["live_hazards"][0]["id"] == active_id

    # 4. Call optimize-routes and verify the safety penalty and ETA delay are applied
    payload_opt = {
        "routes": [
            {
                "route_id": "safest_alternative",
                "route_type": "safest",
                "distance_km": 10.5,
                "duration_min": 20.0,
                "waypoints": [
                    [12.9716, 77.5946],
                    [12.9300, 77.6200],  # Passes through the active hazard
                    [12.9170, 77.6230]
                ]
            }
        ]
    }
    response = client.post("/api/navigation/optimize-routes", json=payload_opt, headers=_auth_headers)
    assert response.status_code == 200
    opt_data = response.json()
    
    # Verify the evaluated alternative route
    opt_route = opt_data["routes"][0]
    assert opt_route["active_hazards_nearby"] == 1
    assert len(opt_route["live_hazards"]) == 1
    # Expected delay: Road blocked (15.0 mins base for Critical)
    assert opt_route["expected_delay_minutes"] >= 15.0
    # Combined duration (duration_min + delays)
    assert opt_route["eta_minutes"] >= 35.0

    # 5. Cleanup active hazard so it doesn't affect subsequent test suites
    response_cleanup = client.put(f"/api/hazards/{active_id}/resolve", headers=_auth_headers)
    assert response_cleanup.status_code == 200


def test_lstm_traffic_prediction_pipeline():
    """Phase 8: Test TomTom manual traffic collection, LSTM training pipeline (test mode), and LSTM prediction inference."""
    db = SessionLocal()
    try:
        import os
        from app.models.traffic import TrafficData

        # 1. Test manual collection endpoint
        res_collect = client.post("/api/traffic/collect", headers=_auth_headers)
        assert res_collect.status_code == 200
        data_coll = res_collect.json()
        assert data_coll["status"] == "success"
        assert "stored_count" in data_coll

        # 2. Test LSTM training pipeline with insufficient data warning
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.commit()

        res_train_fail = client.post("/api/predict/train-lstm?is_test=true", headers=_auth_headers)
        assert res_train_fail.status_code == 200
        data_train_fail = res_train_fail.json()
        assert data_train_fail["status"] == "insufficient_data"
        assert "More data is required" in data_train_fail["message"]

        # 3. Seed test observations for training
        # We need 120 observations for Junction 1 (Silk Board)
        now = datetime.now()
        for i in range(125):
            ts = now - timedelta(hours=125 - i)
            speed_ratio = 0.8 - (i % 5) * 0.05
            obs = TrafficData(
                junction_id=1,
                latitude=12.9170,
                longitude=77.6230,
                timestamp=ts,
                vehicle_count=0,
                avg_speed=50.0 * speed_ratio,
                free_flow_speed=50.0,
                speed_ratio=speed_ratio,
                day_of_week=ts.weekday(),
                hour_of_day=ts.hour,
                is_test=True
            )
            db.add(obs)
        db.commit()

        # 4. Trigger training on the seeded test observations
        res_train_success = client.post("/api/predict/train-lstm?is_test=true", headers=_auth_headers)
        assert res_train_success.status_code == 200
        data_train_success = res_train_success.json()
        assert data_train_success["status"] == "success"
        assert "Successfully trained LSTM" in data_train_success["message"]

        # 5. Verify LSTM prediction works using the trained test model
        payload_pred = {
            "junction_id": 1,
            "hours_ahead": 5,
            "use_test_model": True
        }
        res_pred = client.post("/api/predict/traffic", json=payload_pred, headers=_auth_headers)
        assert res_pred.status_code == 200
        data_pred = res_pred.json()
        assert data_pred["junction_id"] == 1
        assert len(data_pred["predictions"]) == 5
        for p in data_pred["predictions"]:
            assert p["prediction_source"] == "lstm_model"
            assert "predicted_vehicle_count" in p
            assert "congestion_level" in p
            assert p["confidence"] == 0.90

        # 6. Verify that requesting production model (default) falls back to heuristic if no prod model exists
        payload_pred_prod = {
            "junction_id": 1,
            "hours_ahead": 5,
            "use_test_model": False
        }
        res_pred_prod = client.post("/api/predict/traffic", json=payload_pred_prod, headers=_auth_headers)
        assert res_pred_prod.status_code == 200
        data_pred_prod = res_pred_prod.json()
        for p in data_pred_prod["predictions"]:
            assert p["prediction_source"] == "hour_pattern_baseline"

        # 7. Cleanup test observations and generated test models/scalers
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.commit()

        ml_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ml", "models",
        )
        for filename in ["traffic_lstm_test.h5", "traffic_scaler_test.pkl"]:
            path = os.path.join(ml_dir, filename)
            if os.path.exists(path):
                os.remove(path)

    finally:
        db.close()


def test_user_data_isolation():
    """Phase 9: Verify user data isolation on road hazards (modifications) and route history."""
    db = SessionLocal()
    try:
        from app.models.user import User
        from app.middleware.auth import hash_pin, create_access_token

        # Ensure userB is registered
        email_b = "user_b_isolation_test@example.com"
        user_b = db.query(User).filter(User.email == email_b).first()
        if not user_b:
            user_b = User(
                email=email_b,
                username=email_b,
                hashed_password="",
                email_verified=True,
                pin_hash=hash_pin("123456"),
                is_active=True,
            )
            db.add(user_b)
            db.commit()
            db.refresh(user_b)

        token_b = create_access_token(data={"sub": str(user_b.id)})
        auth_headers_b = {"Authorization": f"Bearer {token_b}"}

        # 2. Report a hazard as User A (current_user)
        payload_hazard = {
            "hazard_type": "Accident",
            "severity": "High",
            "latitude": 12.9170,
            "longitude": 77.6230,
            "description": "User A road hazard report"
        }
        res_hazard = client.post("/api/hazards", json=payload_hazard, headers=_auth_headers)
        assert res_hazard.status_code == 201
        hazard_data = res_hazard.json()
        hazard_id = hazard_data["id"]

        # 3. Try to resolve User A's hazard using User B's auth headers (should fail with 403)
        res_resolve_fail = client.put(f"/api/hazards/{hazard_id}/resolve", headers=auth_headers_b)
        assert res_resolve_fail.status_code == 403
        assert "do not have permission" in res_resolve_fail.json()["detail"]

        # 4. Resolve the hazard as User A (should succeed)
        res_resolve_ok = client.put(f"/api/hazards/{hazard_id}/resolve", headers=_auth_headers)
        assert res_resolve_ok.status_code == 200

        # Clean up User B
        db.delete(user_b)
        db.commit()
    finally:
        db.close()


def test_global_exception_handling():
    """Phase 9: Verify unhandled exceptions are masked and logged, returning generic 500 responses."""
    # Register dynamic test route that raises exception
    from app.main import app as fastapi_app
    
    @fastapi_app.get("/api/test-exception-endpoint")
    def trigger_internal_exception():
        raise Exception("Sensitive DB Connection string: postgres://admin:secret@db.host:5432/db")

    # Send request and verify details are masked
    response = client.get("/api/test-exception-endpoint")
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "internal server error occurred" in data["detail"]
    assert "postgres" not in data["detail"]  # No credentials exposed
    assert "secret" not in data["detail"]


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
        ("Road Hazards Endpoint", test_road_hazards_endpoint),
        ("Dynamic Hazard routing updates Endpoint", test_dynamic_hazard_routing_endpoint),
        ("LSTM Traffic Collection & Training Pipeline Endpoint", test_lstm_traffic_prediction_pipeline),
        ("User Data Isolation Endpoint", test_user_data_isolation),
        ("Global Exception Handling Endpoint", test_global_exception_handling),
    ]
    print(f"Running NAVISCAPE Backend API Test Suite ({len(tests)} integration tests)...")
    for name, test_func in tests:
        test_func()
        print(f"[PASS] {name}")
    print(f"\nALL {len(tests)} BACKEND INTEGRATION TESTS PASSED SUCCESSFULLY!")
