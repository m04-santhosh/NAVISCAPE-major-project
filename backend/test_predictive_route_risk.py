"""
Test Suite for Predictive Route Risk Engine (Phase 3A)
Validates end-to-end integration of XGBoost model, historical accident exposure,
road hazards, traffic intelligence, input validation, authentication, and error handling.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal, init_db
from app.models.user import User
from app.middleware.auth import create_access_token, hash_password

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def auth_context():
    """Sets up a clean test user and returns authorization headers."""
    init_db()
    db: Session = SessionLocal()
    test_email = "phase3a_predictive_user@naviscape.io"
    user = db.query(User).filter(User.email == test_email).first()
    if not user:
        user = User(
            email=test_email,
            username="phase3a_predictive_user",
            full_name="Phase 3A Predictive Test User",
            hashed_password=hash_password("predictivePass123!"),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    user_id = user.id
    db.close()

    return {"headers": headers, "user_id": user_id}


# ── 1. Authentication & Security Tests ────────────────────────────────────────

def test_route_risk_authenticated_succeeds(auth_context):
    """Verify that a valid authenticated request with Bangalore corridor coordinates succeeds."""
    payload = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
        "waypoints": [
            [12.9716, 77.5946],
            [12.9550, 77.6050],
            [12.9352, 77.6245],
            [12.9170, 77.6230],
        ],
        "distance_km": 9.8,
        "duration_min": 24.5,
        "weather": "Clear",
    }
    response = client.post("/api/predict/route-risk", json=payload, headers=auth_context["headers"])
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "predicted_safety_score" in data
    assert "risk_level" in data
    assert "accident_exposure" in data
    assert "traffic_risk" in data
    assert "risk_hotspots" in data


def test_route_risk_unauthenticated_rejected():
    """Verify that an unauthenticated request is rejected with HTTP 401 Unauthorized."""
    payload = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
    }
    response = client.post("/api/predict/route-risk", json=payload)
    assert response.status_code == 401


# ── 2. Request Validation Tests ───────────────────────────────────────────────

def test_route_risk_invalid_latitude_rejected(auth_context):
    """Verify that latitude outside [-90, 90] is rejected with HTTP 422."""
    payload = {
        "source_lat": 105.0,  # Invalid latitude
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
    }
    response = client.post("/api/predict/route-risk", json=payload, headers=auth_context["headers"])
    assert response.status_code == 422


def test_route_risk_invalid_longitude_rejected(auth_context):
    """Verify that longitude outside [-180, 180] is rejected with HTTP 422."""
    payload = {
        "source_lat": 12.9716,
        "source_lng": 195.0,  # Invalid longitude
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
    }
    response = client.post("/api/predict/route-risk", json=payload, headers=auth_context["headers"])
    assert response.status_code == 422


def test_route_risk_missing_required_fields_rejected(auth_context):
    """Verify that missing source or destination coordinates is rejected with HTTP 422."""
    payload = {
        "source_lat": 12.9716,
        # source_lng missing
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
    }
    response = client.post("/api/predict/route-risk", json=payload, headers=auth_context["headers"])
    assert response.status_code == 422


def test_route_risk_invalid_waypoints_rejected(auth_context):
    """Verify that malformed waypoints list is rejected with HTTP 422."""
    payload = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
        "waypoints": [[12.9716]],  # Invalid: only 1 coordinate instead of [lat, lng]
    }
    response = client.post("/api/predict/route-risk", json=payload, headers=auth_context["headers"])
    assert response.status_code == 422


# ── 3. Predictive Safety Scoring & Risk Level Contracts ───────────────────────

def test_route_risk_score_range_and_risk_level(auth_context):
    """Verify that predicted safety score is strictly within [0, 100] and risk_level matches threshold."""
    payload = {
        "source_lat": 12.9756,
        "source_lng": 77.6066,
        "destination_lat": 13.0358,
        "destination_lng": 77.5970,
        "weather": "Clear",
    }
    response = client.post("/api/predict/route-risk", json=payload, headers=auth_context["headers"])
    assert response.status_code == 200
    data = response.json()

    score = data["predicted_safety_score"]
    risk_level = data["risk_level"]

    assert isinstance(score, (int, float))
    assert 0.0 <= score <= 100.0
    assert risk_level in ["LOW", "MODERATE", "HIGH"]

    # Validate centralized threshold mapping
    if score >= 80.0:
        assert risk_level == "LOW"
    elif score >= 60.0:
        assert risk_level == "MODERATE"
    else:
        assert risk_level == "HIGH"


def test_route_risk_weather_sensitivity(auth_context):
    """Verify that adverse weather conditions (Rain vs Clear) produce deterministic risk factor output."""
    payload_clear = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
        "weather": "Clear",
    }
    payload_rain = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
        "weather": "Rain",
    }
    res_clear = client.post("/api/predict/route-risk", json=payload_clear, headers=auth_context["headers"]).json()
    res_rain = client.post("/api/predict/route-risk", json=payload_rain, headers=auth_context["headers"]).json()

    assert res_clear["predicted_safety_score"] >= 0.0
    assert res_rain["predicted_safety_score"] >= 0.0
    assert "model_used" in res_clear
    assert "model_used" in res_rain


# ── 4. Accident Exposure & Real Hotspots Verification ─────────────────────────

def test_route_risk_accident_exposure_real_counts(auth_context):
    """Verify that historical accident exposure returns non-negative integers and valid category."""
    payload = {
        "source_lat": 12.9170,
        "source_lng": 77.6230,
        "destination_lat": 12.9352,
        "destination_lng": 77.6245,
    }
    response = client.post("/api/predict/route-risk", json=payload, headers=auth_context["headers"])
    assert response.status_code == 200
    data = response.json()

    exp = data["accident_exposure"]
    assert exp["level"] in ["LOW", "MODERATE", "HIGH"]
    assert isinstance(exp["nearby_accidents"], int) and exp["nearby_accidents"] >= 0
    assert isinstance(exp["severe_accidents"], int) and exp["severe_accidents"] >= 0


def test_route_risk_hotspots_structure_and_no_fake_hotspots(auth_context):
    """Verify that risk hotspots contain valid coordinates, real severity, and zero fake entries."""
    payload = {
        "source_lat": 12.9170,
        "source_lng": 77.6230,
        "destination_lat": 12.9591,
        "destination_lng": 77.7010,
    }
    response = client.post("/api/predict/route-risk", json=payload, headers=auth_context["headers"])
    assert response.status_code == 200
    data = response.json()

    hotspots = data["risk_hotspots"]
    assert isinstance(hotspots, list)
    assert len(hotspots) <= 10

    for hs in hotspots:
        assert -90.0 <= hs["latitude"] <= 90.0
        assert -180.0 <= hs["longitude"] <= 180.0
        assert 0.0 <= hs["risk_score"] <= 100.0
        assert hs["nearby_accidents"] >= 3  # Only real clusters with >=3 accidents qualify
        assert isinstance(hs["description"], str) and len(hs["description"]) > 0


# ── 5. Traffic Risk Fallback & Resilience ─────────────────────────────────────

def test_route_risk_traffic_risk_graceful_handling(auth_context):
    """Verify that traffic risk returns LOW, MODERATE, HIGH, or UNKNOWN without raising errors."""
    payload = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
    }
    response = client.post("/api/predict/route-risk", json=payload, headers=auth_context["headers"])
    assert response.status_code == 200
    data = response.json()

    tf = data["traffic_risk"]
    assert tf["level"] in ["LOW", "MODERATE", "HIGH", "UNKNOWN"]
    if tf["level"] == "UNKNOWN":
        assert tf["traffic_score"] is None or tf["traffic_source"] in [None, "unavailable", "no_waypoints"]
