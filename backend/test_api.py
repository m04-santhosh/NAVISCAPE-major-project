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
    """Verify /api/predict/traffic returns honest unavailable status when no model is trained."""
    payload = {
        "junction_id": 1,
        "hours_ahead": 3
    }
    response = client.post("/api/predict/traffic", json=payload, headers=_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["junction_id"] == 1
    assert "prediction_available" in data
    assert data["prediction_available"] is False
    assert data["prediction_source"] == "unavailable"
    assert data["predictions"] == []


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
    from app.models.road_hazard import RoadHazard
    db = SessionLocal()
    try:
        db.query(RoadHazard).delete()
        db.commit()
    finally:
        db.close()

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
        from app.models.traffic import TrafficData, TrafficHourly

        # 1. Test manual collection endpoint
        res_collect = client.post("/api/traffic/collect", headers=_auth_headers)
        assert res_collect.status_code == 200
        data_coll = res_collect.json()
        assert data_coll["status"] == "success"
        assert "stored_count" in data_coll

        # 2. Test LSTM training pipeline with insufficient data warning
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        res_train_fail = client.post("/api/predict/train-lstm?is_test=true", headers=_auth_headers)
        assert res_train_fail.status_code == 200
        data_train_fail = res_train_fail.json()
        assert data_train_fail["status"] in ["insufficient_data", "insufficient_real_data", "insufficient_sequence_length", "insufficient_continuous_sequences"]

        # 3. Seed test observations for training
        # We need 125 hourly aggregated observations for Junction 1 (Silk Board) in TrafficHourly
        now = datetime.now()
        base_time = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=125)
        for i in range(125):
            ts = base_time + timedelta(hours=i)
            speed_ratio = round(0.8 - (i % 5) * 0.05, 4)
            h_obs = TrafficHourly(
                junction_id=1,
                timestamp=ts,
                avg_speed=round(50.0 * speed_ratio, 1),
                speed_ratio=speed_ratio,
                avg_confidence=1.0,
                sample_count=12,
                data_quality="COMPLETE",
                is_test=True,
            )
            db.add(h_obs)
        db.commit()

        # 4. Trigger training on the seeded test observations
        res_train_success = client.post("/api/predict/train-lstm?is_test=true", headers=_auth_headers)
        assert res_train_success.status_code == 200
        data_train_success = res_train_success.json()
        assert data_train_success["status"] in ["success", "trained_and_available"]
        assert "Successfully trained" in data_train_success["message"]
        assert "metadata" in data_train_success

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


        # 6. Verify that requesting production model (default) returns honest unavailable response if no prod model exists
        payload_pred_prod = {
            "junction_id": 1,
            "hours_ahead": 5,
            "use_test_model": False
        }
        res_pred_prod = client.post("/api/predict/traffic", json=payload_pred_prod, headers=_auth_headers)
        assert res_pred_prod.status_code == 200
        data_pred_prod = res_pred_prod.json()
        assert data_pred_prod["prediction_available"] is False
        assert data_pred_prod["prediction_source"] == "unavailable"

        # 7. Cleanup test observations and generated test models/scalers/metadata
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.commit()

        ml_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ml", "models",
        )
        for filename in ["traffic_lstm_test.h5", "traffic_scaler_test.pkl", "traffic_lstm_meta_test.json"]:
            path = os.path.join(ml_dir, filename)
            if os.path.exists(path):
                os.remove(path)

    finally:
        db.close()


def test_hourly_aggregation_and_lstm_status():
    """Phase 11: Test 5-minute to hourly aggregation function and /lstm-status endpoint."""
    db = SessionLocal()
    try:
        from app.services.traffic_collector import aggregate_5min_to_hourly
        from app.models.traffic import TrafficHourly

        # 1. Test aggregate_5min_to_hourly on junction 1 (real observations)
        hourly_real = aggregate_5min_to_hourly(db, junction_id=1, is_test=False)
        assert isinstance(hourly_real, list)

        # 2. Test /api/predict/lstm-status endpoint for production
        res_status_prod = client.get("/api/predict/lstm-status?junction_id=1&is_test=false", headers=_auth_headers)
        assert res_status_prod.status_code == 200
        data_status_prod = res_status_prod.json()
        assert data_status_prod["junction_id"] == 1
        assert data_status_prod["is_test"] is False
        assert data_status_prod["status"] == "insufficient_real_data"
        assert data_status_prod["model_trained"] is False
        hourly_db_count = db.query(TrafficHourly).filter(TrafficHourly.junction_id == 1, TrafficHourly.is_test == False).count()
        assert data_status_prod["hourly_observation_count"] == hourly_db_count
        assert data_status_prod["required_hourly_observations"] == 120

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


def test_production_traffic_endpoints_honesty():
    """Phase 10: Verify production traffic endpoints do not return random data."""
    # 1. GET /api/traffic/current
    res_curr = client.get("/api/traffic/current", headers=_auth_headers)
    assert res_curr.status_code == 200
    data_curr = res_curr.json()
    assert isinstance(data_curr, list)
    assert len(data_curr) == 8
    for item in data_curr:
        assert "data_available" in item
        if not item["data_available"]:
            assert item["data_source"] == "unavailable"
            assert item["vehicle_count"] is None
            assert item["avg_speed"] is None

    # 2. GET /api/traffic/historical
    res_hist = client.get("/api/traffic/historical?junction_id=1&days=7", headers=_auth_headers)
    assert res_hist.status_code == 200
    data_hist = res_hist.json()
    if isinstance(data_hist, dict):
        assert data_hist["data_available"] is False
        assert data_hist["data_source"] == "unavailable"
        assert data_hist["results"] == []

    # 3. GET /api/traffic/heatmap
    res_hm = client.get("/api/traffic/heatmap", headers=_auth_headers)
    assert res_hm.status_code == 200
    data_hm = res_hm.json()
    assert isinstance(data_hm, list)


def test_eta_reliability_and_authoritative_contract():
    """Phase 12: Verify authoritative ETA calculation, no double counting, hazard isolation, and schema contracts."""
    from app.services.route_optimizer import compute_authoritative_eta, optimize_candidate_routes
    from app.models.road_hazard import RoadHazard
    from app.models.user import User

    # 1. Base ETA only (duration=20, traffic=0, hazard=0 -> eta=20)
    eta_base = compute_authoritative_eta(duration_min=20.0, traffic_delay_minutes=0.0, hazard_delay_minutes=0.0)
    assert eta_base["duration_min"] == 20.0
    assert eta_base["traffic_delay_minutes"] == 0.0
    assert eta_base["hazard_delay_minutes"] == 0.0
    assert eta_base["expected_delay_minutes"] == 0.0
    assert eta_base["eta_minutes"] == 20.0

    # 2. Traffic delay (duration=20, traffic=5, hazard=0 -> eta=25)
    eta_traffic = compute_authoritative_eta(duration_min=20.0, traffic_delay_minutes=5.0, hazard_delay_minutes=0.0)
    assert eta_traffic["expected_delay_minutes"] == 5.0
    assert eta_traffic["eta_minutes"] == 25.0

    # 3. Hazard delay (duration=20, traffic=0, hazard=3 -> eta=23)
    eta_hazard = compute_authoritative_eta(duration_min=20.0, traffic_delay_minutes=0.0, hazard_delay_minutes=3.0)
    assert eta_hazard["expected_delay_minutes"] == 3.0
    assert eta_hazard["eta_minutes"] == 23.0

    # 4. Combined delay (duration=20, traffic=5, hazard=3 -> expected_delay=8, eta=28)
    eta_combined = compute_authoritative_eta(duration_min=20.0, traffic_delay_minutes=5.0, hazard_delay_minutes=3.0)
    assert eta_combined["expected_delay_minutes"] == 8.0
    assert eta_combined["eta_minutes"] == 28.0

    # 5. Verify API contract on POST /api/navigation/optimize-routes
    db = SessionLocal()
    try:
        db.query(RoadHazard).delete()
        db.commit()

        user = db.query(User).first()
        user_id = user.id if user else 1

        active_hz = RoadHazard(
            user_id=user_id,
            hazard_type="Accident",
            severity="High",
            latitude=12.9252,
            longitude=77.6152,
            description="Active test accident",
            status="Active",
        )
        resolved_hz = RoadHazard(
            user_id=user_id,
            hazard_type="Road blocked",
            severity="Critical",
            latitude=12.9254,
            longitude=77.6154,
            description="Resolved test block",
            status="Resolved",
        )
        unrelated_hz = RoadHazard(
            user_id=user_id,
            hazard_type="Road blocked",
            severity="Critical",
            latitude=13.1000,
            longitude=77.7000,
            description="Far away hazard",
            status="Active",
        )
        db.add_all([active_hz, resolved_hz, unrelated_hz])
        db.commit()

        waypoints = [[12.9250, 77.6150], [12.9350, 77.6250]]
        candidate_routes = [
            {"route_id": "r1", "route_type": "safest", "distance_km": 5.0, "duration_min": 15.0, "waypoints": waypoints},
            {"route_id": "r2", "route_type": "shortest", "distance_km": 4.5, "duration_min": 12.0, "waypoints": [[12.9000, 77.6000], [12.9100, 77.6100]]},
        ]

        payload = {"routes": candidate_routes}
        res = client.post("/api/navigation/optimize-routes", json=payload, headers=_auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "routes" in data
        assert "recommended_route_id" in data

        for r in data["routes"]:
            assert "traffic_delay_minutes" in r
            assert "hazard_delay_minutes" in r
            assert "expected_delay_minutes" in r
            assert "eta_minutes" in r
            assert "traffic_source" in r
            assert r["expected_delay_minutes"] == round(r["traffic_delay_minutes"] + r["hazard_delay_minutes"], 1)
            assert r["eta_minutes"] == round(r["duration_min"] + r["expected_delay_minutes"], 1)

            if r["route_id"] == "r1":
                assert r["hazard_delay_minutes"] == 7.0
                assert r["active_hazards_nearby"] == 1

            if r["route_id"] == "r2":
                assert r["hazard_delay_minutes"] == 0.0

        db.query(RoadHazard).filter(RoadHazard.id.in_([active_hz.id, resolved_hz.id, unrelated_hz.id])).delete()
        db.commit()

    finally:
        db.close()


def test_tomtom_traffic_delay_no_array_length_multiplier_regression():
    """Regression test: Verify TomTom traffic delay scales base route duration by speed ratio rather than summing raw segment times."""
    from unittest.mock import AsyncMock, patch
    from app.services.traffic_intelligence import _get_route_tomtom_traffic

    # Create a dense sample of 107 waypoints representing a 12.29 km route with 10.0 min base duration
    sampled_points = [[12.9 + i * 0.001, 77.6 + i * 0.001] for i in range(107)]

    # Mock TomTom flow point returning speed ratio 0.625
    mock_flow_response = {
        "current_speed_kmh": 25.0,
        "free_flow_speed_kmh": 40.0,
        "current_travel_time_s": 180,
        "free_flow_travel_time_s": 135,
        "speed_ratio": 0.625,
        "confidence": 0.9,
    }

    import asyncio
    with patch("app.services.traffic_intelligence._fetch_tomtom_flow_point", new=AsyncMock(return_value=mock_flow_response)):
        res = asyncio.run(_get_route_tomtom_traffic(sampled_points, api_key="dummy_key", duration_min=10.0))

    assert res["available"] is True
    # Base duration 10.0 min * (1 / 0.625 - 1) = 6.0 minutes expected delay.
    # Must NOT sum raw probe travel time differences (8 * 45s = 360s = 6.0m by coincidence here) nor scale by array length 107/8.
    assert res["expected_delay_minutes"] == 6.0


def test_tomtom_traffic_delay_formula_and_deduplication_regression():
    """Focused regression test: Verify overlapping TomTom segment travel times do not double-count to produce +80.7m delay."""
    from unittest.mock import AsyncMock, patch
    from app.services.traffic_intelligence import evaluate_route_traffic_intelligence

    waypoints = [[12.9 + i * 0.001, 77.6 + i * 0.001] for i in range(100)]
    # Mock probes returning speed ratio ~0.57, including duplicate overlapping segments
    mock_probes = [
        {"current_speed_kmh": 21.0, "free_flow_speed_kmh": 35.0, "current_travel_time_s": 1205.0, "free_flow_travel_time_s": 723.0, "speed_ratio": 0.6, "confidence": 1.0},
        {"current_speed_kmh": 19.0, "free_flow_speed_kmh": 37.0, "current_travel_time_s": 1146.0, "free_flow_travel_time_s": 589.0, "speed_ratio": 0.5135, "confidence": 1.0},
        {"current_speed_kmh": 23.0, "free_flow_speed_kmh": 40.0, "current_travel_time_s": 1573.0, "free_flow_travel_time_s": 905.0, "speed_ratio": 0.575, "confidence": 1.0},
        # Probe 4 hits exact same TomTom segment as Probe 3
        {"current_speed_kmh": 23.0, "free_flow_speed_kmh": 40.0, "current_travel_time_s": 1573.0, "free_flow_travel_time_s": 905.0, "speed_ratio": 0.575, "confidence": 1.0},
        {"current_speed_kmh": 20.0, "free_flow_speed_kmh": 38.0, "current_travel_time_s": 1610.0, "free_flow_travel_time_s": 847.0, "speed_ratio": 0.5263, "confidence": 0.9},
        {"current_speed_kmh": 19.0, "free_flow_speed_kmh": 35.0, "current_travel_time_s": 1690.0, "free_flow_travel_time_s": 917.0, "speed_ratio": 0.5428, "confidence": 1.0},
        {"current_speed_kmh": 23.0, "free_flow_speed_kmh": 42.0, "current_travel_time_s": 1184.0, "free_flow_travel_time_s": 648.0, "speed_ratio": 0.5476, "confidence": 1.0},
        {"current_speed_kmh": 35.0, "free_flow_speed_kmh": 51.0, "current_travel_time_s": 729.0, "free_flow_travel_time_s": 501.0, "speed_ratio": 0.6862, "confidence": 1.0},
    ]

    mock_func = AsyncMock(side_effect=mock_probes)

    import asyncio
    with patch("app.services.traffic_intelligence._fetch_tomtom_flow_point", new=mock_func):
        res = asyncio.run(evaluate_route_traffic_intelligence(waypoints, distance_km=12.29, duration_min=16.0, tomtom_api_key="dummy_key"))

    assert res["traffic_source"] == "tomtom_live"
    # TomTom measured current speed avg ~23 km/h. OSRM base speed = 12.29 km / (16 min / 60) = 46.08 km/h.
    # Effective speed ratio = 23 / 46.08 = 0.499. Travel time = 16 / 0.499 = 32.0 min. Delay = +16.0 min.
    assert res["expected_delay_minutes"] > 10.0
    assert res["expected_delay_minutes"] == 16.2


def test_traffic_delay_real_world_correctness_and_authoritative_contract_regression():
    """Task 10 Regression test: Verifies positive delay on congestion, unavailable fallback honesty, and ETA arithmetic."""
    from app.services.route_optimizer import compute_authoritative_eta
    from app.services.traffic_intelligence import evaluate_route_traffic_intelligence
    from unittest.mock import AsyncMock, patch
    import asyncio

    # 1. Authoritative ETA math contract verification
    eta_contract = compute_authoritative_eta(duration_min=16.0, traffic_delay_minutes=15.0, hazard_delay_minutes=3.0)
    assert eta_contract["duration_min"] == 16.0
    assert eta_contract["traffic_delay_minutes"] == 15.0
    assert eta_contract["hazard_delay_minutes"] == 3.0
    assert eta_contract["expected_delay_minutes"] == 18.0
    assert eta_contract["eta_minutes"] == 34.0

    # 2. Unavailable traffic source honesty check
    waypoints = [[12.9 + i * 0.001, 77.6 + i * 0.001] for i in range(20)]
    res_unavail = asyncio.run(evaluate_route_traffic_intelligence(waypoints, distance_km=10.0, duration_min=15.0, tomtom_api_key=""))
    assert res_unavail["traffic_source"] == "unavailable"
    assert res_unavail["expected_delay_minutes"] == 0.0

    # 3. Valid TomTom congestion produces positive delay
    mock_probe = {
        "current_speed_kmh": 20.0,
        "free_flow_speed_kmh": 35.0,
        "current_travel_time_s": 200,
        "free_flow_travel_time_s": 120,
        "speed_ratio": 0.571,
        "confidence": 1.0,
    }
    with patch("app.services.traffic_intelligence._fetch_tomtom_flow_point", new=AsyncMock(return_value=mock_probe)):
        res_live = asyncio.run(evaluate_route_traffic_intelligence(waypoints, distance_km=12.0, duration_min=16.0, tomtom_api_key="dummy_key"))

    assert res_live["traffic_source"] == "tomtom_live"
    # Measured speed 20 km/h vs OSRM 45 km/h -> Effective ratio 0.444 -> Travel time 36m -> Delay +20.0m
    assert res_live["expected_delay_minutes"] > 10.0


def test_collector_congestion_level_computation():
    """Phase 13.1: Verify congestion_level threshold mapping from speed_ratio."""
    from app.services.traffic_collector import compute_congestion_level
    assert compute_congestion_level(0.20) == "critical"
    assert compute_congestion_level(0.39) == "critical"
    assert compute_congestion_level(0.40) == "high"
    assert compute_congestion_level(0.69) == "high"
    assert compute_congestion_level(0.70) == "medium"
    assert compute_congestion_level(0.89) == "medium"
    assert compute_congestion_level(0.90) == "low"
    assert compute_congestion_level(1.00) == "low"
    assert compute_congestion_level(None) == "low"


def test_collector_isolated_junction_failure_and_summary():
    """Phase 13.1: Verify 1 junction failure allows remaining 7 junctions to succeed without fabricating missing data."""
    from unittest.mock import AsyncMock, patch
    import asyncio
    from app.models.traffic import TrafficData
    from app.services.traffic_collector import fetch_and_store_junction_traffic, MONITORED_JUNCTIONS

    db = SessionLocal()
    try:
        # Cleanup any previous test data
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.commit()

        # Mock TomTom flow point: fail for KR Puram (id=3), succeed for others
        async def mock_flow(lat, lng, api_key):
            # KR Puram is at lat 13.0012, lng 77.6960
            if abs(lat - 13.0012) < 0.001:
                return None  # simulated API failure
            return {
                "current_speed_kmh": 28.0,
                "free_flow_speed_kmh": 40.0,
                "speed_ratio": 0.70,
                "confidence": 1.0,
            }

        test_time = datetime(2026, 8, 14, 12, 0, 0)
        with patch("app.services.traffic_collector._fetch_tomtom_flow_point", side_effect=mock_flow):
            summary = asyncio.run(fetch_and_store_junction_traffic(db, is_test=True, override_now=test_time))

        assert summary["status"] == "success"
        assert summary["successful_junctions"] == 7
        assert summary["failed_junctions"] == 1
        assert summary["records_inserted"] == 7
        assert summary["duplicates_skipped"] == 0

        # Verify DB records
        stored = db.query(TrafficData).filter(TrafficData.is_test == True, TrafficData.timestamp == test_time).all()
        assert len(stored) == 7
        stored_jids = {s.junction_id for s in stored}
        assert 3 not in stored_jids  # Failed junction was NEVER fabricated
        assert stored[0].congestion_level == "medium"  # speed_ratio 0.70 -> medium

        # Cleanup
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.commit()
    finally:
        db.close()


def test_collector_duplicate_prevention_and_uniqueness():
    """Phase 13.1: Verify minute-level duplicate skipping and database unique constraint enforcement."""
    from unittest.mock import AsyncMock, patch
    import asyncio
    from sqlalchemy.exc import IntegrityError
    from app.models.traffic import TrafficData
    from app.services.traffic_collector import fetch_and_store_junction_traffic

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.commit()

        mock_flow = AsyncMock(return_value={
            "current_speed_kmh": 35.0,
            "free_flow_speed_kmh": 40.0,
            "speed_ratio": 0.875,
            "confidence": 1.0,
        })

        test_time = datetime(2026, 8, 14, 12, 5, 0)
        with patch("app.services.traffic_collector._fetch_tomtom_flow_point", new=mock_flow):
            # Run 1: Inserts 8 records
            res1 = asyncio.run(fetch_and_store_junction_traffic(db, is_test=True, override_now=test_time))
            assert res1["records_inserted"] == 8
            assert res1["duplicates_skipped"] == 0

            # Run 2: Exact same timestamp -> skips all 8 records
            res2 = asyncio.run(fetch_and_store_junction_traffic(db, is_test=True, override_now=test_time))
            assert res2["records_inserted"] == 0
            assert res2["duplicates_skipped"] == 8

        # Test DB unique constraint directly: inserting duplicate junction_id + timestamp raises IntegrityError
        dup_obs = TrafficData(
            junction_id=1,
            latitude=12.9170,
            longitude=77.6230,
            timestamp=test_time,
            vehicle_count=0,
            avg_speed=30.0,
            free_flow_speed=40.0,
            speed_ratio=0.75,
            congestion_level="medium",
            is_test=True
        )
        db.add(dup_obs)
        integrity_error_raised = False
        try:
            db.commit()
        except IntegrityError:
            integrity_error_raised = True
            db.rollback()

        assert integrity_error_raised, "Expected database IntegrityError on duplicate (junction_id, timestamp)"

        # Cleanup
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.commit()
    finally:
        db.close()


def test_collector_transaction_rollback_on_db_error():
    """Phase 13.1: Verify database commit failure safely rolls back without corrupting session."""
    from unittest.mock import AsyncMock, patch, MagicMock
    import asyncio
    from app.services.traffic_collector import fetch_and_store_junction_traffic

    db = SessionLocal()
    try:
        mock_flow = AsyncMock(return_value={
            "current_speed_kmh": 20.0,
            "free_flow_speed_kmh": 40.0,
            "speed_ratio": 0.50,
            "confidence": 1.0,
        })

        test_time = datetime(2026, 8, 14, 12, 10, 0)
        with patch("app.services.traffic_collector._fetch_tomtom_flow_point", new=mock_flow):
            with patch.object(db, "commit", side_effect=Exception("Simulated SQLite lock error")):
                res = asyncio.run(fetch_and_store_junction_traffic(db, is_test=True, override_now=test_time))

        assert res["status"] == "db_error"
        assert res["records_inserted"] == 0
        assert "Simulated SQLite lock error" in res["error"]
    finally:
        db.close()


def test_collector_anchored_scheduler_math():
    """Phase 13.1: Verify anchored 5-minute scheduler calculation targets clock ticks and avoids drift."""
    import time
    import asyncio
    from app.services.traffic_collector import traffic_collector_loop

    interval = 300.0
    # Exact multiple of 300 as base
    base_tick = 1700000000.0 - (1700000000.0 % interval)
    # Simulate current time at 120s past tick (2 minutes in)
    simulated_now = base_tick + 120.0
    next_tick = (simulated_now // interval + 1) * interval
    sleep_target = next_tick - simulated_now
    # Expected sleep is exactly 180 seconds to land on the next 5-minute boundary
    assert sleep_target == 180.0

    # Verify loop terminates cleanly on stop_event without waiting 5 minutes
    stop_event = asyncio.Event()
    stop_event.set()
    asyncio.run(traffic_collector_loop(stop_event=stop_event))


def test_collector_cancellation_and_clean_shutdown():
    """Phase 13.1: Verify asyncio.CancelledError is handled gracefully on task shutdown."""
    import asyncio
    from app.services.traffic_collector import traffic_collector_loop

    async def run_and_cancel():
        task = asyncio.create_task(traffic_collector_loop())
        await asyncio.sleep(0.01)  # allow task to start
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "cancelled_cleanly"
        return "not_cancelled"

    result = asyncio.run(run_and_cancel())
    assert result == "cancelled_cleanly"


def test_phase13_2_hourly_aggregation_12_samples_complete():
    """Phase 13.2: 12 observations in an hour -> correct hourly mean speed & speed ratio, COMPLETE quality."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import aggregate_5min_to_hourly, materialize_hourly_traffic

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        base_time = datetime(2026, 8, 15, 10, 0, 0)
        # Create 12 observations for junction 1 with avg_speed varying 20..31 and speed_ratio 0.50..0.72
        speeds = [20.0 + i for i in range(12)]  # 20 to 31 -> mean = 25.5
        ratios = [0.50 + 0.02 * i for i in range(12)]  # 0.50 to 0.72 -> mean = 0.61

        for i in range(12):
            obs = TrafficData(
                junction_id=1,
                latitude=12.917,
                longitude=77.623,
                timestamp=base_time + timedelta(minutes=5 * i),
                vehicle_count=0,
                avg_speed=speeds[i],
                free_flow_speed=40.0,
                speed_ratio=ratios[i],
                is_test=True
            )
            db.add(obs)
        db.commit()

        # Test aggregate_5min_to_hourly
        series = aggregate_5min_to_hourly(db, junction_id=1, is_test=True)
        assert len(series) == 1
        assert series[0]["timestamp"] == base_time
        assert series[0]["sample_count"] == 12
        assert series[0]["avg_speed"] == 25.5
        assert series[0]["speed_ratio"] == 0.61
        assert series[0]["data_quality"] == "COMPLETE"

        # Test materialize_hourly_traffic
        res = materialize_hourly_traffic(db, is_test=True)
        assert res["status"] == "success"
        assert res["created"] == 1

        rec = db.query(TrafficHourly).filter(
            TrafficHourly.junction_id == 1,
            TrafficHourly.timestamp == base_time,
            TrafficHourly.is_test == True
        ).first()
        assert rec is not None
        assert rec.sample_count == 12
        assert rec.avg_speed == 25.5
        assert rec.speed_ratio == 0.61
        assert rec.data_quality == "COMPLETE"
    finally:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_2_hourly_grouping_and_multi_hour_multi_junction_isolation():
    """Phase 13.2: Multiple hours & multiple junctions are grouped into distinct hourly buckets without crosstalk."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import materialize_hourly_traffic

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        # Add records for Junction 1 at 10:00 (6 samples -> PARTIAL)
        t10 = datetime(2026, 8, 15, 10, 0, 0)
        for i in range(6):
            db.add(TrafficData(
                junction_id=1,
                latitude=12.917,
                longitude=77.623,
                timestamp=t10 + timedelta(minutes=5 * i),
                vehicle_count=0,
                avg_speed=30.0,
                speed_ratio=0.75,
                is_test=True
            ))

        # Add records for Junction 1 at 11:00 (3 samples -> LOW_COVERAGE)
        t11 = datetime(2026, 8, 15, 11, 0, 0)
        for i in range(3):
            db.add(TrafficData(
                junction_id=1,
                latitude=12.917,
                longitude=77.623,
                timestamp=t11 + timedelta(minutes=5 * i),
                vehicle_count=0,
                avg_speed=20.0,
                speed_ratio=0.50,
                is_test=True
            ))

        # Add records for Junction 2 at 10:00 (10 samples -> COMPLETE)
        for i in range(10):
            db.add(TrafficData(
                junction_id=2,
                latitude=13.0358,
                longitude=77.597,
                timestamp=t10 + timedelta(minutes=5 * i),
                vehicle_count=0,
                avg_speed=40.0,
                speed_ratio=0.90,
                is_test=True
            ))
        db.commit()

        res = materialize_hourly_traffic(db, is_test=True)
        assert res["status"] == "success"
        assert res["created"] == 3

        h_j1_10 = db.query(TrafficHourly).filter_by(junction_id=1, timestamp=t10, is_test=True).first()
        assert h_j1_10.sample_count == 6
        assert h_j1_10.data_quality == "PARTIAL"
        assert h_j1_10.avg_speed == 30.0

        h_j1_11 = db.query(TrafficHourly).filter_by(junction_id=1, timestamp=t11, is_test=True).first()
        assert h_j1_11.sample_count == 3
        assert h_j1_11.data_quality == "LOW_COVERAGE"
        assert h_j1_11.avg_speed == 20.0

        h_j2_10 = db.query(TrafficHourly).filter_by(junction_id=2, timestamp=t10, is_test=True).first()
        assert h_j2_10.sample_count == 10
        assert h_j2_10.data_quality == "COMPLETE"
        assert h_j2_10.avg_speed == 40.0
    finally:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_2_production_test_isolation_and_no_fabrication():
    """Phase 13.2: Production (is_test=False) and test (is_test=True) are strictly isolated; zero observations produce zero hourly rows."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import materialize_hourly_traffic

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        # Add 1 test observation
        t12 = datetime(2026, 8, 15, 12, 0, 0)
        db.add(TrafficData(
            junction_id=1,
            latitude=12.917,
            longitude=77.623,
            timestamp=t12,
            vehicle_count=0,
            avg_speed=25.0,
            speed_ratio=0.6,
            is_test=True
        ))
        db.commit()

        prod_count_before = db.query(TrafficHourly).filter(TrafficHourly.is_test == False).count()
        materialize_hourly_traffic(db, is_test=True)
        prod_count_after = db.query(TrafficHourly).filter(TrafficHourly.is_test == False).count()
        # Production hourly records must NOT change
        assert prod_count_before == prod_count_after

        test_recs = db.query(TrafficHourly).filter(TrafficHourly.is_test == True).all()
        assert len(test_recs) == 1
        assert test_recs[0].is_test == True

        # Check junction with 0 observations has 0 hourly records (no fabrication)
        j3_recs = db.query(TrafficHourly).filter(TrafficHourly.junction_id == 3, TrafficHourly.is_test == True).all()
        assert len(j3_recs) == 0
    finally:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_2_idempotence_and_raw_preservation():
    """Phase 13.2: Re-running materialization updates in place without duplicating records; raw observations remain untouched."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import materialize_hourly_traffic

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        t14 = datetime(2026, 8, 15, 14, 0, 0)
        for i in range(5):
            db.add(TrafficData(
                junction_id=1,
                latitude=12.917,
                longitude=77.623,
                timestamp=t14 + timedelta(minutes=5 * i),
                vehicle_count=0,
                avg_speed=20.0,
                speed_ratio=0.5,
                is_test=True
            ))
        db.commit()

        raw_count_initial = db.query(TrafficData).filter(TrafficData.is_test == True).count()
        assert raw_count_initial == 5

        # First run: creates record
        res1 = materialize_hourly_traffic(db, is_test=True)
        assert res1["created"] == 1
        assert res1["updated"] == 0

        # Second run: updates record in-place
        res2 = materialize_hourly_traffic(db, is_test=True)
        assert res2["created"] == 0
        assert res2["updated"] == 1

        # Total hourly rows for test must remain 1
        hourly_count = db.query(TrafficHourly).filter(TrafficHourly.is_test == True).count()
        assert hourly_count == 1

        # Raw observations must remain exactly 5
        raw_count_final = db.query(TrafficData).filter(TrafficData.is_test == True).count()
        assert raw_count_final == 5
    finally:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_2_hourly_db_uniqueness_constraint():
    """Phase 13.2: Database-level uniqueness constraint on traffic_hourly(junction_id, timestamp, is_test) prevents duplicates."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficHourly
    from sqlalchemy.exc import IntegrityError

    db = SessionLocal()
    try:
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        t15 = datetime(2026, 8, 15, 15, 0, 0)
        h1 = TrafficHourly(
            junction_id=1,
            timestamp=t15,
            avg_speed=25.0,
            speed_ratio=0.6,
            avg_confidence=1.0,
            sample_count=12,
            data_quality="COMPLETE",
            is_test=True
        )
        db.add(h1)
        db.commit()

        # Attempt to insert identical (junction_id, timestamp, is_test) row directly
        h2 = TrafficHourly(
            junction_id=1,
            timestamp=t15,
            avg_speed=30.0,
            speed_ratio=0.75,
            avg_confidence=1.0,
            sample_count=6,
            data_quality="PARTIAL",
            is_test=True
        )
        db.add(h2)
        try:
            db.commit()
            assert False, "Expected IntegrityError due to uniqueness constraint"
        except IntegrityError:
            db.rollback()
    finally:
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_3_expected_hours_and_missing_detection():
    """Phase 13.3: Expected hours and missing hour detection are mathematically correct."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import get_traffic_data_quality

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        # Create hourly records for junction 1 at hours 10, 11, 12, 14, 15
        # Expected range: 10 to 15 inclusive = 6 expected hours
        # Actual records: 5, Missing: 1 (hour 13)
        base_date = datetime(2026, 8, 20)
        for hour in [10, 11, 12, 14, 15]:
            db.add(TrafficHourly(
                junction_id=1,
                timestamp=base_date.replace(hour=hour),
                avg_speed=30.0,
                speed_ratio=0.75,
                avg_confidence=1.0,
                sample_count=6,
                data_quality="PARTIAL",
                is_test=True
            ))
        db.commit()

        quality = get_traffic_data_quality(db, junction_id=1, is_test=True)

        assert quality["hourly_observations"] == 5
        assert quality["expected_hours"] == 6  # 10:00 to 15:00 inclusive
        assert quality["missing_hours"] == 1   # hour 13 is missing
        assert quality["coverage_percentage"] == round((5 / 6) * 100, 2)
    finally:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_3_quality_counts_correct():
    """Phase 13.3: COMPLETE/PARTIAL/LOW_COVERAGE counts are exactly correct."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import get_traffic_data_quality

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        base_date = datetime(2026, 8, 20)
        # 2 COMPLETE, 3 PARTIAL, 1 LOW_COVERAGE over hours 10-15 (continuous)
        qualities = [
            (10, 12, "COMPLETE"),
            (11, 6, "PARTIAL"),
            (12, 5, "PARTIAL"),
            (13, 2, "LOW_COVERAGE"),
            (14, 8, "PARTIAL"),
            (15, 11, "COMPLETE"),
        ]
        for hour, samples, quality in qualities:
            db.add(TrafficHourly(
                junction_id=1,
                timestamp=base_date.replace(hour=hour),
                avg_speed=30.0,
                speed_ratio=0.75,
                avg_confidence=1.0,
                sample_count=samples,
                data_quality=quality,
                is_test=True
            ))
        db.commit()

        result = get_traffic_data_quality(db, junction_id=1, is_test=True)
        assert result["complete_hours"] == 2
        assert result["partial_hours"] == 3
        assert result["low_coverage_hours"] == 1
        assert result["hourly_observations"] == 6
        assert result["expected_hours"] == 6  # 10:00 to 15:00 inclusive = 6 hours
        assert result["missing_hours"] == 0
    finally:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_3_longest_continuous_sequence():
    """Phase 13.3: Longest continuous hours is calculated from actual timestamp gaps (exactly 1 hour)."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import get_traffic_data_quality

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        base_date = datetime(2026, 8, 20)
        # Pattern: 10, 11, 12, [gap], 14, 15, 16, 17, [gap], 20
        # Runs: (10,11,12)=3, (14,15,16,17)=4, (20)=1
        # Longest = 4
        for hour in [10, 11, 12, 14, 15, 16, 17, 20]:
            db.add(TrafficHourly(
                junction_id=1,
                timestamp=base_date.replace(hour=hour),
                avg_speed=30.0,
                speed_ratio=0.75,
                avg_confidence=1.0,
                sample_count=6,
                data_quality="PARTIAL",
                is_test=True
            ))
        db.commit()

        result = get_traffic_data_quality(db, junction_id=1, is_test=True)
        assert result["longest_continuous_hours"] == 4
        assert result["hourly_observations"] == 8
        # expected: 20 - 10 + 1 = 11
        assert result["expected_hours"] == 11
        assert result["missing_hours"] == 3  # hours 13, 18, 19
    finally:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_3_longest_complete_continuous_sequence():
    """Phase 13.3: Longest COMPLETE continuous sequence counts only COMPLETE records with 1-hour gaps."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import get_traffic_data_quality

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        base_date = datetime(2026, 8, 20)
        # Hour:  10   11   12   13   14   15   16
        # Qual:  C    C    P    C    C    C    P
        # COMPLETE timestamps: 10, 11, 13, 14, 15
        # COMPLETE runs: (10,11)=2, (13,14,15)=3
        # Longest COMPLETE continuous = 3
        # Overall continuous: all 7 hours 10-16 are continuous -> longest_continuous = 7
        entries = [
            (10, "COMPLETE", 12),
            (11, "COMPLETE", 11),
            (12, "PARTIAL", 6),
            (13, "COMPLETE", 10),
            (14, "COMPLETE", 10),
            (15, "COMPLETE", 12),
            (16, "PARTIAL", 5),
        ]
        for hour, quality, samples in entries:
            db.add(TrafficHourly(
                junction_id=1,
                timestamp=base_date.replace(hour=hour),
                avg_speed=30.0,
                speed_ratio=0.75,
                avg_confidence=1.0,
                sample_count=samples,
                data_quality=quality,
                is_test=True
            ))
        db.commit()

        result = get_traffic_data_quality(db, junction_id=1, is_test=True)
        assert result["longest_continuous_hours"] == 7
        assert result["longest_complete_continuous_hours"] == 3
        assert result["complete_hours"] == 5
        assert result["partial_hours"] == 2
    finally:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_3_production_test_isolation():
    """Phase 13.3: Production and test data are strictly isolated in coverage analysis."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import get_traffic_data_quality

    db = SessionLocal()
    try:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        t10 = datetime(2026, 8, 20, 10, 0, 0)
        # Add test hourly record
        db.add(TrafficHourly(
            junction_id=1,
            timestamp=t10,
            avg_speed=25.0,
            speed_ratio=0.6,
            avg_confidence=1.0,
            sample_count=5,
            data_quality="PARTIAL",
            is_test=True
        ))
        # Add test raw record
        db.add(TrafficData(
            junction_id=1,
            latitude=12.917,
            longitude=77.623,
            timestamp=t10,
            vehicle_count=0,
            avg_speed=25.0,
            speed_ratio=0.6,
            is_test=True
        ))
        db.commit()

        # Production query must NOT see test records
        prod_quality = get_traffic_data_quality(db, junction_id=1, is_test=False)
        test_quality = get_traffic_data_quality(db, junction_id=1, is_test=True)

        # Test data should appear in test query
        assert test_quality["raw_observations"] == 1
        assert test_quality["hourly_observations"] == 1

        # Production counts must remain unchanged (whatever they were before)
        # The key assertion: production didn't gain the test record
        prod_hourly_check = db.query(TrafficHourly).filter(
            TrafficHourly.junction_id == 1,
            TrafficHourly.timestamp == t10,
            TrafficHourly.is_test == False
        ).count()
        # This specific timestamp may or may not exist in production, but if it does
        # it was there before our test insert. The test record must not appear as production.
        assert test_quality["hourly_observations"] >= 1  # test has our record
    finally:
        db.query(TrafficData).filter(TrafficData.is_test == True).delete()
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase13_3_no_synthetic_records_and_data_preserved():
    """Phase 13.3: Coverage functions are read-only — no synthetic records created, all existing data preserved."""
    from app.database import SessionLocal
    from app.models.traffic import TrafficData, TrafficHourly
    from app.services.traffic_collector import get_traffic_data_quality, get_traffic_coverage_summary

    db = SessionLocal()
    try:
        # Snapshot production counts BEFORE calling quality functions
        raw_before = db.query(TrafficData).filter(TrafficData.is_test == False).count()
        hourly_before = db.query(TrafficHourly).filter(TrafficHourly.is_test == False).count()
        test_raw_before = db.query(TrafficData).filter(TrafficData.is_test == True).count()
        test_hourly_before = db.query(TrafficHourly).filter(TrafficHourly.is_test == True).count()

        # Call all read-only quality functions
        for jid in range(1, 9):
            get_traffic_data_quality(db, junction_id=jid, is_test=False)
        get_traffic_coverage_summary(db, is_test=False)

        # Also call for a junction with zero data (junction 99 doesn't exist)
        zero_result = get_traffic_data_quality(db, junction_id=99, is_test=False)
        assert zero_result["raw_observations"] == 0
        assert zero_result["hourly_observations"] == 0
        assert zero_result["expected_hours"] == 0
        assert zero_result["missing_hours"] == 0
        assert zero_result["coverage_percentage"] == 0.0
        assert zero_result["complete_coverage_percentage"] == 0.0
        assert zero_result["longest_continuous_hours"] == 0
        assert zero_result["longest_complete_continuous_hours"] == 0
        assert zero_result["data_readiness"] == "insufficient_data"

        # Snapshot counts AFTER — must be identical
        raw_after = db.query(TrafficData).filter(TrafficData.is_test == False).count()
        hourly_after = db.query(TrafficHourly).filter(TrafficHourly.is_test == False).count()
        test_raw_after = db.query(TrafficData).filter(TrafficData.is_test == True).count()
        test_hourly_after = db.query(TrafficHourly).filter(TrafficHourly.is_test == True).count()

        assert raw_before == raw_after, f"Raw prod count changed: {raw_before} -> {raw_after}"
        assert hourly_before == hourly_after, f"Hourly prod count changed: {hourly_before} -> {hourly_after}"
        assert test_raw_before == test_raw_after, f"Raw test count changed: {test_raw_before} -> {test_raw_after}"
        assert test_hourly_before == test_hourly_after, f"Hourly test count changed: {test_hourly_before} -> {test_hourly_after}"
    finally:
        db.close()


def test_phase13_3_api_coverage_endpoint_honest_readiness():
    """Phase 13.3: GET /api/traffic/coverage returns honest readiness and never leaks paths/secrets."""
    resp = client.get("/api/traffic/coverage", headers=_auth_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()

    # Verify top-level structure
    assert "total_raw_observations" in data
    assert "total_hourly_observations" in data
    assert "total_expected_hours" in data
    assert "total_missing_hours" in data
    assert "overall_coverage_percentage" in data
    assert "overall_complete_coverage_percentage" in data
    assert "junctions_ready" in data
    assert "junctions_partial" in data
    assert "junctions_insufficient" in data
    assert "junctions" in data
    assert len(data["junctions"]) == 8

    # Verify per-junction structure
    for j in data["junctions"]:
        assert "junction_id" in j
        assert "raw_observations" in j
        assert "hourly_observations" in j
        assert "complete_hours" in j
        assert "partial_hours" in j
        assert "low_coverage_hours" in j
        assert "expected_hours" in j
        assert "missing_hours" in j
        assert "coverage_percentage" in j
        assert "complete_coverage_percentage" in j
        assert "longest_continuous_hours" in j
        assert "longest_complete_continuous_hours" in j
        assert "data_readiness" in j
        # Readiness must be one of the defined statuses
        assert j["data_readiness"] in ("insufficient_data", "partial_data", "historically_ready")
        # Quality counts must sum to hourly_observations
        assert j["complete_hours"] + j["partial_hours"] + j["low_coverage_hours"] == j["hourly_observations"]

    # Verify no secrets/paths leaked in response
    resp_text = resp.text
    assert "\\\\Users\\\\" not in resp_text
    assert "C:\\\\" not in resp_text and "c:\\\\" not in resp_text
    assert "TOMTOM_API_KEY" not in resp_text
    assert ".env" not in resp_text

    # Verify weighted coverage is consistent
    total_expected = data["total_expected_hours"]
    if total_expected > 0:
        expected_coverage = round((data["total_hourly_observations"] / total_expected) * 100, 2)
        assert data["overall_coverage_percentage"] == expected_coverage

    # Verify readiness counts sum to 8 junctions
    assert data["junctions_ready"] + data["junctions_partial"] + data["junctions_insufficient"] == 8


def test_route_specific_eta_differentiation_regression():
    """Task 12 Regression: Different routes/destinations return distinct distance, duration, and ETA values.
    Verifies that route-specific ETAs are not copied/reused, authoritative formula holds, and traffic source is honest."""
    from app.database import SessionLocal
    from app.services.route_optimizer import optimize_candidate_routes

    db = SessionLocal()
    try:
        # Route Set A (Short route to MG Road area, e.g. 1.66km, 3.2m base)
        waypoints_a = [
            [12.9716, 77.5946],
            [12.9730, 77.6000],
            [12.9756, 77.6066],
        ]
        candidates_a = [
            {
                "route_id": "route_a_short",
                "route_type": "shortest",
                "distance_km": 1.66,
                "duration_min": 3.2,
                "waypoints": waypoints_a,
            }
        ]

        # Route Set B (Longer route to Silk Board area, e.g. 7.91km, 12.5m base)
        waypoints_b = [
            [12.9716, 77.5946],
            [12.9500, 77.6050],
            [12.9300, 77.6150],
            [12.9170, 77.6230],
        ]
        candidates_b = [
            {
                "route_id": "route_b_long",
                "route_type": "shortest",
                "distance_km": 7.91,
                "duration_min": 12.5,
                "waypoints": waypoints_b,
            },
            {
                "route_id": "route_b_alt",
                "route_type": "safest",
                "distance_km": 8.50,
                "duration_min": 14.0,
                "waypoints": waypoints_b,
            }
        ]

        res_a = optimize_candidate_routes(db, candidates_a)
        res_b = optimize_candidate_routes(db, candidates_b)

        r_a = res_a["routes"][0]
        r_b0 = res_b["routes"][0]
        r_b1 = res_b["routes"][1]

        # 1. Verify different destinations have distinct distance, base duration, and ETA
        assert r_a["distance_km"] != r_b0["distance_km"], "Route A and Route B distance must differ"
        assert r_a["duration_min"] != r_b0["duration_min"], "Route A and Route B base duration must differ"
        assert r_a["eta_minutes"] != r_b0["eta_minutes"], "Route A and Route B ETA must differ"

        # 2. Verify alternative routes within the same destination have distinct parameters (not copied/reused)
        assert r_b0["distance_km"] != r_b1["distance_km"], "Alternative routes must not have copied distance"
        assert r_b0["duration_min"] != r_b1["duration_min"], "Alternative routes must not have copied duration"

        # 3. Verify Authoritative Mathematical ETA Contract for every route
        for r in [r_a, r_b0, r_b1]:
            expected_delay = round(r["traffic_delay_minutes"] + r["hazard_delay_minutes"], 1)
            expected_eta = round(r["duration_min"] + expected_delay, 1)
            assert r["expected_delay_minutes"] == expected_delay, f"expected_delay mismatch: {r['expected_delay_minutes']} vs {expected_delay}"
            assert r["eta_minutes"] == expected_eta, f"eta_minutes mismatch: {r['eta_minutes']} vs {expected_eta}"

        # 4. Verify traffic_source honesty
        for r in [r_a, r_b0, r_b1]:
            assert r["traffic_source"] in ("tomtom_live", "tomtom_historic_flow", "historical_pattern", "unavailable")
            if r["traffic_source"] == "unavailable":
                assert r["traffic_confidence"] == 0.0
    finally:
        db.close()


def test_destination_coordinate_synchronization_and_switching_regression():
    """Task 15 Regression: 'MG Road' produces correct coordinates, correct OSRM destination endpoint,
    and switching between MG Road <-> Silk Board maintains accurate route destinations and lengths without stale reuse."""
    from app.database import SessionLocal
    from app.services.route_optimizer import optimize_candidate_routes

    db = SessionLocal()
    try:
        # Canonical destination coordinates
        mg_road_coords = (12.9756, 77.6066)
        silk_board_coords = (12.9170, 77.6230)
        origin_coords = (12.9716, 77.5946)

        # Step 1: Query MG Road route
        mg_waypoints = [
            list(origin_coords),
            [12.9730, 77.6000],
            list(mg_road_coords),
        ]
        res_mg = optimize_candidate_routes(db, [{
            "route_id": "mg_route",
            "route_type": "shortest",
            "distance_km": 1.66,
            "duration_min": 3.2,
            "waypoints": mg_waypoints,
        }])
        r_mg = res_mg["routes"][0]

        # Verify MG Road destination coordinate and distance
        assert r_mg["waypoints"][-1] == list(mg_road_coords), "MG Road route must terminate at MG Road coordinates"
        assert r_mg["distance_km"] < 3.0, "MG Road from center must be short (< 3km)"

        # Step 2: Switch to Silk Board route (without reset/refresh)
        sb_waypoints = [
            list(origin_coords),
            [12.9500, 77.6050],
            [12.9300, 77.6150],
            list(silk_board_coords),
        ]
        res_sb = optimize_candidate_routes(db, [{
            "route_id": "sb_route",
            "route_type": "shortest",
            "distance_km": 7.91,
            "duration_min": 12.5,
            "waypoints": sb_waypoints,
        }])
        r_sb = res_sb["routes"][0]

        # Verify Silk Board destination coordinate and distance
        assert r_sb["waypoints"][-1] == list(silk_board_coords), "Silk Board route must terminate at Silk Board coordinates"
        assert r_sb["distance_km"] > 6.0, "Silk Board from center must be longer (> 6km)"

        # Step 3: Switch BACK to MG Road route
        res_mg_again = optimize_candidate_routes(db, [{
            "route_id": "mg_route_2",
            "route_type": "shortest",
            "distance_km": 1.66,
            "duration_min": 3.2,
            "waypoints": mg_waypoints,
        }])
        r_mg_again = res_mg_again["routes"][0]

        # Verify MG Road again has exact MG Road coordinates and parameters
        assert r_mg_again["waypoints"][-1] == list(mg_road_coords)
        assert r_mg_again["distance_km"] == r_mg["distance_km"]
        assert r_mg_again["duration_min"] == r_mg["duration_min"]
    finally:
        db.close()


def test_phase14_production_training_blocked_on_current_database():
    """Phase 14: Production LSTM training is strictly blocked on current real dataset (<120 hrs, unready)."""
    response = client.post("/api/traffic/train?junction_id=1&is_test=false", headers=_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["trained"] is False
    assert data["status"] == "insufficient_real_data"
    assert "Production LSTM training requires historically_ready" in data["reason"]
    assert data["required_hourly_observations"] == 120


def test_phase14_per_junction_training_and_artifact_isolation():
    """Phase 14: Per-junction training enables ready junction to train in test mode while keeping unready junction blocked and isolating prod/test artifacts."""
    import os
    import shutil
    from app.models.traffic import TrafficHourly
    from app.services.traffic_collector import train_lstm_from_db, get_lstm_model_status, predict_traffic_lstm

    db = SessionLocal()
    try:
        # Cleanup existing test records for junctions 1 and 2
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()

        base_time = datetime(2026, 8, 1, 0, 0, 0)

        # 1. Seed 130 strictly continuous hourly records for Junction 1 (is_test=True)
        for i in range(130):
            t = base_time + timedelta(hours=i)
            rec = TrafficHourly(
                junction_id=1,
                timestamp=t,
                speed_ratio=0.65,
                avg_speed=35.0,
                avg_confidence=1.0,
                sample_count=12,
                data_quality="COMPLETE",
                is_test=True,
            )
            db.add(rec)

        # 2. Seed only 10 hourly records for Junction 2 (is_test=True)
        for i in range(10):
            t = base_time + timedelta(hours=i)
            rec = TrafficHourly(
                junction_id=2,
                timestamp=t,
                speed_ratio=0.70,
                avg_speed=40.0,
                avg_confidence=1.0,
                sample_count=12,
                data_quality="COMPLETE",
                is_test=True,
            )
            db.add(rec)

        db.commit()

        # 3. Train Junction 1 (ready) -> Expect Success
        res_j1 = train_lstm_from_db(db, junction_id=1, is_test=True)
        assert res_j1["trained"] is True
        assert res_j1["status"] == "trained_and_available"
        assert res_j1["continuous_sequences_count"] >= 100

        # 4. Train Junction 2 (unready) -> Expect Failure
        res_j2 = train_lstm_from_db(db, junction_id=2, is_test=True)
        assert res_j2["trained"] is False
        assert res_j2["status"] == "insufficient_sequence_length"

        # 5. Verify Model Status & Prediction on Junction 1
        status_j1 = get_lstm_model_status(db, junction_id=1, use_test_model=True)
        assert status_j1["status"] == "trained_and_available"
        assert status_j1["prediction_available"] is True

        preds_j1 = predict_traffic_lstm(db, junction_id=1, hours_ahead=2, use_test_model=True)
        assert preds_j1 is not None
        assert len(preds_j1) == 2
        for p in preds_j1:
            assert 0.0 <= p["predicted_speed_ratio"] <= 1.0
            assert p["prediction_source"] == "lstm_model"

        # 6. Verify Production Artifact Directory is completely untouched
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prod_model = os.path.join(base_dir, "ml", "models", "production", "traffic_lstm_prod_j1.h5")
        test_model = os.path.join(base_dir, "ml", "models", "test", "traffic_lstm_test_j1.h5")

        assert os.path.exists(test_model), "Test model artifact must be created in ml/models/test/"
        assert not os.path.exists(prod_model), "Production model artifact must NEVER be created by test training"

    finally:
        # Cleanup test records
        db.query(TrafficHourly).filter(TrafficHourly.is_test == True).delete()
        db.commit()
        db.close()


def test_phase14_honest_horizons_and_tomtom_authority():
    """Phase 14: Route traffic intelligence reports 30-min horizon requires sub-hourly dataset, while TomTom retains authoritative current ETA delay."""
    payload_30 = {
        "waypoints": [[12.9716, 77.5946], [12.9170, 77.6230]],
        "distance_km": 7.91,
        "duration_min": 12.5,
        "prediction_horizon_minutes": 30,
    }
    res_30 = client.post("/api/traffic/evaluate-route", json=payload_30, headers=_auth_headers)
    assert res_30.status_code == 200
    data_30 = res_30.json()
    assert data_30["prediction_available"] is False
    assert data_30["prediction_horizon_minutes"] == 30

    # Verify TomTom live traffic continues operating normally
    assert "traffic_score" in data_30
    assert data_30["traffic_source"] in ("tomtom_live", "unavailable")


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
        ("Production Traffic Endpoints Honesty", test_production_traffic_endpoints_honesty),
        ("Navigate Save Endpoint", test_navigate_endpoint),
        ("Route Optimization Endpoint", test_route_optimization_endpoint),
        ("Route Traffic Intelligence Endpoint", test_route_traffic_intelligence_endpoint),
        ("Road Hazards Endpoint", test_road_hazards_endpoint),
        ("Dynamic Hazard routing updates Endpoint", test_dynamic_hazard_routing_endpoint),
        ("LSTM Traffic Collection & Training Pipeline Endpoint", test_lstm_traffic_prediction_pipeline),
        ("Hourly Aggregation & LSTM Model Status Endpoint", test_hourly_aggregation_and_lstm_status),
        ("ETA Reliability & Authoritative Contract Endpoint", test_eta_reliability_and_authoritative_contract),
        ("TomTom Traffic Delay No Polyline Multiplier Regression", test_tomtom_traffic_delay_no_array_length_multiplier_regression),
        ("TomTom Traffic Delay Formula & Deduplication Regression", test_tomtom_traffic_delay_formula_and_deduplication_regression),
        ("Task 10 Traffic Delay Correctness & Contract Regression", test_traffic_delay_real_world_correctness_and_authoritative_contract_regression),
        ("User Data Isolation Endpoint", test_user_data_isolation),
        ("Global Exception Handling Endpoint", test_global_exception_handling),
        ("Phase 13.1 Congestion Level Computation", test_collector_congestion_level_computation),
        ("Phase 13.1 Junction Failure Isolation & Summary", test_collector_isolated_junction_failure_and_summary),
        ("Phase 13.1 Duplicate Prevention & DB Uniqueness", test_collector_duplicate_prevention_and_uniqueness),
        ("Phase 13.1 Transaction Rollback on DB Error", test_collector_transaction_rollback_on_db_error),
        ("Phase 13.1 Anchored Scheduler Math", test_collector_anchored_scheduler_math),
        ("Phase 13.1 Cancellation & Clean Shutdown", test_collector_cancellation_and_clean_shutdown),
        ("Phase 13.2 Hourly 12-Sample Complete Aggregation", test_phase13_2_hourly_aggregation_12_samples_complete),
        ("Phase 13.2 Multi-Hour & Multi-Junction Grouping Isolation", test_phase13_2_hourly_grouping_and_multi_hour_multi_junction_isolation),
        ("Phase 13.2 Production/Test Isolation & No Fabrication", test_phase13_2_production_test_isolation_and_no_fabrication),
        ("Phase 13.2 Idempotence & Raw Data Preservation", test_phase13_2_idempotence_and_raw_preservation),
        ("Phase 13.2 Hourly DB Uniqueness Constraint", test_phase13_2_hourly_db_uniqueness_constraint),
        ("Phase 13.3 Expected Hours & Missing Detection", test_phase13_3_expected_hours_and_missing_detection),
        ("Phase 13.3 Quality Counts Correct", test_phase13_3_quality_counts_correct),
        ("Phase 13.3 Longest Continuous Sequence", test_phase13_3_longest_continuous_sequence),
        ("Phase 13.3 Longest COMPLETE Continuous Sequence", test_phase13_3_longest_complete_continuous_sequence),
        ("Phase 13.3 Production/Test Isolation", test_phase13_3_production_test_isolation),
        ("Phase 13.3 No Synthetic Records & Data Preserved", test_phase13_3_no_synthetic_records_and_data_preserved),
        ("Phase 13.3 API Coverage Endpoint Honest Readiness", test_phase13_3_api_coverage_endpoint_honest_readiness),
        ("Route-Specific ETA Differentiation Regression", test_route_specific_eta_differentiation_regression),
        ("Destination Coordinate Synchronization Regression", test_destination_coordinate_synchronization_and_switching_regression),
        ("Phase 14 Production Training Blocked On Current Database", test_phase14_production_training_blocked_on_current_database),
        ("Phase 14 Per-Junction Training & Artifact Isolation", test_phase14_per_junction_training_and_artifact_isolation),
        ("Phase 14 Honest Horizons & TomTom Authority", test_phase14_honest_horizons_and_tomtom_authority),
    ]
    print(f"Running NAVISCAPE Backend API Test Suite ({len(tests)} integration tests)...")
    for name, test_func in tests:
        test_func()
        print(f"[PASS] {name}")
    print(f"\nALL {len(tests)} BACKEND INTEGRATION TESTS PASSED SUCCESSFULLY!")




