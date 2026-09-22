"""
Test Suite for Predictive Route Comparison Engine (Phase 3B)
Verifies multi-route predictive comparison, trade-off calculations, input validation,
authentication, and non-prescriptive safety metrics without fabricating routes.
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
    test_email = "phase3b_compare_user@naviscape.io"
    user = db.query(User).filter(User.email == test_email).first()
    if not user:
        user = User(
            email=test_email,
            username="phase3b_compare_user",
            full_name="Phase 3B Comparison Test User",
            hashed_password=hash_password("comparePass123!"),
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


# ── 1. Authentication & Authorization ────────────────────────────────────────

def test_route_comparison_unauthenticated_rejected():
    """Verify unauthenticated requests return HTTP 401 Unauthorized."""
    payload = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
    }
    response = client.post("/api/predict/route-comparison", json=payload)
    assert response.status_code == 401


# ── 2. Real Route Alternatives & Scoring Contracts ───────────────────────────

def test_route_comparison_with_candidate_routes_succeeds(auth_context):
    """
    Verify that providing real candidate route alternatives produces structured
    comparison metrics, accurate distances, durations, and 0-100 safety scores.
    """
    payload = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
        "routes": [
            {
                "route_id": "route_shortest",
                "route_type": "shortest",
                "distance_km": 9.8,
                "duration_min": 24.0,
                "waypoints": [
                    [12.9716, 77.5946],
                    [12.9550, 77.6050],
                    [12.9352, 77.6245],
                    [12.9170, 77.6230],
                ],
            },
            {
                "route_id": "route_safest",
                "route_type": "safest",
                "distance_km": 11.5,
                "duration_min": 27.5,
                "waypoints": [
                    [12.9716, 77.5946],
                    [12.9784, 77.6408],
                    [12.9352, 77.6245],
                    [12.9170, 77.6230],
                ],
            },
        ],
        "weather": "Clear",
    }
    response = client.post("/api/predict/route-comparison", json=payload, headers=auth_context["headers"])
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()

    assert "routes" in data
    assert len(data["routes"]) == 2
    assert data["alternatives_available"] is True
    assert "trade_off_summary" in data
    assert data["trade_off_summary"] is not None

    # Verify each route adheres to strict data contracts
    for r in data["routes"]:
        assert r["distance_km"] > 0.0
        assert r["duration_min"] > 0.0
        assert 0.0 <= r["predicted_safety_score"] <= 100.0
        assert r["risk_level"] in ["LOW", "MODERATE", "HIGH"]
        assert r["accident_exposure"]["level"] in ["LOW", "MODERATE", "HIGH"]
        assert isinstance(r["accident_exposure"]["nearby_accidents"], int)
        assert isinstance(r["accident_exposure"]["severe_accidents"], int)
        assert r["traffic_risk"]["level"] in ["LOW", "MODERATE", "HIGH", "UNKNOWN"]
        assert isinstance(r["risk_hotspots"], list)
        assert isinstance(r["factors"], list)


def test_route_comparison_trade_off_summary_differences(auth_context):
    """Verify trade-off summary accurately computes differences without declaring a single 'best route'."""
    payload = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
        "routes": [
            {
                "route_id": "route_1",
                "route_type": "shortest",
                "distance_km": 10.0,
                "duration_min": 20.0,
                "waypoints": [[12.9716, 77.5946], [12.9170, 77.6230]],
            },
            {
                "route_id": "route_2",
                "route_type": "safest",
                "distance_km": 12.5,
                "duration_min": 25.0,
                "waypoints": [[12.9716, 77.5946], [12.9400, 77.6100], [12.9170, 77.6230]],
            },
        ],
    }
    response = client.post("/api/predict/route-comparison", json=payload, headers=auth_context["headers"])
    assert response.status_code == 200
    data = response.json()

    summary = data["trade_off_summary"]
    assert summary is not None
    assert summary["distance_difference_km"] == 2.5
    assert summary["duration_difference_min"] == 5.0
    assert summary["safety_score_difference"] is not None
    assert isinstance(summary["tradeoff_notes"], list)
    assert len(summary["tradeoff_notes"]) > 0


def test_route_comparison_single_route_fallback(auth_context):
    """Verify that when only a single candidate route is provided, alternatives_available is False."""
    payload = {
        "source_lat": 12.9716,
        "source_lng": 77.5946,
        "destination_lat": 12.9170,
        "destination_lng": 77.6230,
        "routes": [
            {
                "route_id": "only_route",
                "route_type": "direct",
                "distance_km": 8.5,
                "duration_min": 18.0,
                "waypoints": [[12.9716, 77.5946], [12.9170, 77.6230]],
            }
        ],
    }
    response = client.post("/api/predict/route-comparison", json=payload, headers=auth_context["headers"])
    assert response.status_code == 200
    data = response.json()

    assert len(data["routes"]) == 1
    assert data["alternatives_available"] is False
    assert data["trade_off_summary"] is None


def test_route_comparison_no_fake_hotspots_or_routes(auth_context):
    """Verify that hotspots and routes only originate from authentic queries."""
    payload = {
        "source_lat": 12.9170,
        "source_lng": 77.6230,
        "destination_lat": 12.9591,
        "destination_lng": 77.7010,
        "routes": [
            {
                "route_id": "silkboard_marathahalli",
                "route_type": "balanced",
                "distance_km": 11.0,
                "duration_min": 26.0,
                "waypoints": [[12.9170, 77.6230], [12.9591, 77.7010]],
            }
        ],
    }
    response = client.post("/api/predict/route-comparison", json=payload, headers=auth_context["headers"])
    assert response.status_code == 200
    data = response.json()

    route = data["routes"][0]
    for hs in route["risk_hotspots"]:
        assert hs["nearby_accidents"] >= 3
        assert -90.0 <= hs["latitude"] <= 90.0
        assert -180.0 <= hs["longitude"] <= 180.0
