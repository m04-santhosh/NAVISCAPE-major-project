"""
NAVISCAPE Women Safety Test Suite — WS-1: Real GPS Capture & Emergency Event Backend
Deterministic unit and integration tests covering:

1. Authenticated emergency trigger succeeds (201).
2. Unauthenticated emergency trigger returns 401.
3. Invalid latitude returns 422.
4. Invalid longitude returns 422.
5. Missing latitude returns 422.
6. Missing longitude returns 422.
7. Negative accuracy is rejected if accuracy is supplied (422).
8. Emergency event is stored in database for the authenticated user.
9. Stored event contains the submitted coordinates and accuracy.
10. Stored event has ACTIVE status.
11. User isolation is preserved (User A cannot access User B's events, user_id spoofing ignored/prevented).
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app.models.user import User
from app.models.emergency import EmergencyEvent
from app.middleware.auth import create_access_token, hash_pin

init_db()

client = TestClient(app, raise_server_exceptions=False)


def _get_or_create_user(email: str) -> tuple[User, dict]:
    """Helper to retrieve or create a test user and generate valid JWT authorization headers."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                username=email.split("@")[0],
                hashed_password="",
                email_verified=True,
                pin_hash=hash_pin("123456"),
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        token = create_access_token({"sub": str(user.id), "email": user.email})
        headers = {"Authorization": f"Bearer {token}"}
        return user, headers
    finally:
        db.close()


def _cleanup_user_emergency_events(user_id: int):
    """Clean up emergency events for a given test user."""
    db = SessionLocal()
    try:
        db.query(EmergencyEvent).filter(EmergencyEvent.user_id == user_id).delete()
        db.commit()
    finally:
        db.close()


# ── Test 1: Authenticated emergency trigger succeeds ──────────────────────────

def test_authenticated_emergency_trigger_succeeds():
    """Requirement 1: Authenticated emergency trigger returns 201 with created event data."""
    user, headers = _get_or_create_user("ws1_test_user1@naviscape.test")
    _cleanup_user_emergency_events(user.id)

    payload = {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "accuracy_m": 8.4,
    }
    response = client.post("/api/women-safety/emergency", json=payload, headers=headers)
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

    data = response.json()
    assert data["success"] is True
    assert "emergency_id" in data
    assert "id" in data
    assert data["latitude"] == pytest.approx(12.9716, abs=1e-4)
    assert data["longitude"] == pytest.approx(77.5946, abs=1e-4)
    assert data["accuracy_m"] == pytest.approx(8.4, abs=0.1)
    assert data["status"] == "ACTIVE"
    assert "triggered_at" in data


# ── Test 2: Unauthenticated emergency trigger returns 401 ─────────────────────

def test_unauthenticated_emergency_trigger_returns_401():
    """Requirement 2: Unauthenticated emergency trigger returns 401 Unauthorized."""
    payload = {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "accuracy_m": 8.4,
    }
    # No Authorization header
    response = client.post("/api/women-safety/emergency", json=payload)
    assert response.status_code == 401


# ── Test 3: Invalid latitude returns 422 ──────────────────────────────────────

def test_invalid_latitude_returns_422():
    """Requirement 3: Latitude outside [-90, 90] returns 422 Unprocessable Entity."""
    user, headers = _get_or_create_user("ws1_validation_user@naviscape.test")

    # Greater than 90
    r1 = client.post("/api/women-safety/emergency", json={"latitude": 91.5, "longitude": 77.5946}, headers=headers)
    assert r1.status_code == 422

    # Less than -90
    r2 = client.post("/api/women-safety/emergency", json={"latitude": -90.1, "longitude": 77.5946}, headers=headers)
    assert r2.status_code == 422


# ── Test 4: Invalid longitude returns 422 ─────────────────────────────────────

def test_invalid_longitude_returns_422():
    """Requirement 4: Longitude outside [-180, 180] returns 422 Unprocessable Entity."""
    user, headers = _get_or_create_user("ws1_validation_user@naviscape.test")

    # Greater than 180
    r1 = client.post("/api/women-safety/emergency", json={"latitude": 12.9716, "longitude": 180.5}, headers=headers)
    assert r1.status_code == 422

    # Less than -180
    r2 = client.post("/api/women-safety/emergency", json={"latitude": 12.9716, "longitude": -185.0}, headers=headers)
    assert r2.status_code == 422


# ── Test 5: Missing latitude returns 422 ──────────────────────────────────────

def test_missing_latitude_returns_422():
    """Requirement 5: Missing latitude returns 422 Unprocessable Entity."""
    user, headers = _get_or_create_user("ws1_validation_user@naviscape.test")

    response = client.post("/api/women-safety/emergency", json={"longitude": 77.5946}, headers=headers)
    assert response.status_code == 422


# ── Test 6: Missing longitude returns 422 ─────────────────────────────────────

def test_missing_longitude_returns_422():
    """Requirement 6: Missing longitude returns 422 Unprocessable Entity."""
    user, headers = _get_or_create_user("ws1_validation_user@naviscape.test")

    response = client.post("/api/women-safety/emergency", json={"latitude": 12.9716}, headers=headers)
    assert response.status_code == 422


# ── Test 7: Negative accuracy is rejected if supplied ─────────────────────────

def test_negative_accuracy_rejected():
    """Requirement 7: Negative accuracy_m is rejected with 422 Unprocessable Entity."""
    user, headers = _get_or_create_user("ws1_validation_user@naviscape.test")

    response = client.post("/api/women-safety/emergency", json={
        "latitude": 12.9716,
        "longitude": 77.5946,
        "accuracy_m": -5.0,
    }, headers=headers)
    assert response.status_code == 422


# ── Test 8: Emergency event is stored for the authenticated user ──────────────

def test_emergency_event_stored_for_authenticated_user():
    """Requirement 8: Emergency event is reliably persisted in the database with the user_id."""
    user, headers = _get_or_create_user("ws1_storage_user@naviscape.test")
    _cleanup_user_emergency_events(user.id)

    response = client.post("/api/women-safety/emergency", json={
        "latitude": 12.9716,
        "longitude": 77.5946,
        "accuracy_m": 10.0,
    }, headers=headers)
    assert response.status_code == 201
    created_id = response.json()["id"]

    db = SessionLocal()
    try:
        event = db.query(EmergencyEvent).filter(EmergencyEvent.id == created_id).first()
        assert event is not None
        assert event.user_id == user.id
    finally:
        db.close()


# ── Test 9: Stored event contains the submitted coordinates ───────────────────

def test_stored_event_contains_submitted_coordinates():
    """Requirement 9: Stored event in DB contains the exact submitted latitude, longitude, and accuracy."""
    user, headers = _get_or_create_user("ws1_coords_user@naviscape.test")
    _cleanup_user_emergency_events(user.id)

    test_lat = 13.0827
    test_lng = 80.2707
    test_acc = 4.25

    response = client.post("/api/women-safety/emergency", json={
        "latitude": test_lat,
        "longitude": test_lng,
        "accuracy_m": test_acc,
    }, headers=headers)
    assert response.status_code == 201
    created_id = response.json()["id"]

    db = SessionLocal()
    try:
        event = db.query(EmergencyEvent).filter(EmergencyEvent.id == created_id).first()
        assert event is not None
        assert event.latitude == pytest.approx(test_lat, abs=1e-4)
        assert event.longitude == pytest.approx(test_lng, abs=1e-4)
        assert event.location_accuracy_m == pytest.approx(test_acc, abs=0.01)
    finally:
        db.close()


# ── Test 10: Stored event has ACTIVE status ───────────────────────────────────

def test_stored_event_has_active_status():
    """Requirement 10: Stored event is saved with ACTIVE status."""
    user, headers = _get_or_create_user("ws1_active_status_user@naviscape.test")
    _cleanup_user_emergency_events(user.id)

    response = client.post("/api/women-safety/emergency", json={
        "latitude": 12.9716,
        "longitude": 77.5946,
    }, headers=headers)
    assert response.status_code == 201

    created_id = response.json()["id"]
    db = SessionLocal()
    try:
        event = db.query(EmergencyEvent).filter(EmergencyEvent.id == created_id).first()
        assert event is not None
        assert event.status == "ACTIVE"
    finally:
        db.close()


# ── Test 11: User isolation is preserved ──────────────────────────────────────

def test_user_isolation_preserved():
    """Requirement 11: Strict tenant isolation — User A cannot access or overwrite User B's events."""
    user_a, headers_a = _get_or_create_user("ws1_isolation_a@naviscape.test")
    user_b, headers_b = _get_or_create_user("ws1_isolation_b@naviscape.test")

    _cleanup_user_emergency_events(user_a.id)
    _cleanup_user_emergency_events(user_b.id)

    # User A triggers emergency
    res_a = client.post("/api/women-safety/emergency", json={
        "latitude": 12.9716,
        "longitude": 77.5946,
        "accuracy_m": 5.0,
    }, headers=headers_a)
    assert res_a.status_code == 201
    event_a_id = res_a.json()["id"]

    # Verify User B querying active emergency gets has_active_event = False
    res_b_active = client.get("/api/women-safety/emergency/active", headers=headers_b)
    assert res_b_active.status_code == 200
    assert res_b_active.json()["has_active_event"] is False

    # Verify User B cannot cancel User A's emergency event
    res_b_cancel = client.post(f"/api/women-safety/emergency/{event_a_id}/cancel", headers=headers_b)
    assert res_b_cancel.status_code == 404

    # Verify sending user_id in payload by User B does NOT assign event to User A
    res_b_spoof = client.post("/api/women-safety/emergency", json={
        "user_id": user_a.id,  # Spoofed user_id
        "latitude": 13.0,
        "longitude": 77.0,
    }, headers=headers_b)
    assert res_b_spoof.status_code == 201
    event_b_id = res_b_spoof.json()["id"]

    db = SessionLocal()
    try:
        event_b = db.query(EmergencyEvent).filter(EmergencyEvent.id == event_b_id).first()
        assert event_b.user_id == user_b.id, "Emergency event must be bound strictly to token owner, not payload user_id"
    finally:
        db.close()
