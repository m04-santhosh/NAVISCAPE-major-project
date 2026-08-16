"""
NAVISCAPE Women Safety Test Suite — WS-1 & WS-2
Deterministic unit and integration tests covering:

WS-1 Tests:
1. Emergency profile creation.
2. Emergency profile retrieval.
3. Emergency profile update.
4. Trusted contact creation.
5. Maximum 4 contacts enforcement.
6. Trusted contact update.
7. Trusted contact deletion.
8. Minimum 2 contacts profile-completion logic.
9. Location-sharing consent defaults to false.
10. Consent can be explicitly enabled.
11. User A cannot access User B's emergency profile.
12. User A cannot access User B's trusted contacts.
13. User A cannot update User B's trusted contact.
14. User A cannot delete User B's trusted contact.
15. Invalid phone numbers rejected.
16. Invalid emails rejected.
17. Existing NAVISCAPE data remains unchanged.

WS-2 Tests:
18. test_ws2_sos_requires_authentication
19. test_ws2_sos_requires_complete_women_safety_profile
20. test_ws2_sos_valid_profile_creates_active_event
21. test_ws2_sos_invalid_latitude_rejected
22. test_ws2_sos_invalid_longitude_rejected
23. test_ws2_sos_missing_coordinates_rejected
24. test_ws2_sos_no_fake_location_fallback
25. test_ws2_active_event_retrieval
26. test_ws2_user_isolation
27. test_ws2_user_cannot_cancel_other_user_event
28. test_ws2_active_to_cancelled_transition
29. test_ws2_cancel_preserves_event_record
30. test_ws2_cancel_idempotency
31. test_ws2_duplicate_active_event_prevention
32. test_ws2_existing_database_isolation
33. test_ws2_existing_ws1_functionality
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app.models.user import User
from app.models.emergency_profile import EmergencyProfile, TrustedContact
from app.models.emergency_event import EmergencyEvent
from app.middleware.auth import create_access_token, hash_pin

# Ensure database tables exist
init_db()

client = TestClient(app, raise_server_exceptions=False)


# ── Test Setup Helpers ────────────────────────────────────────────────────────

def _create_test_user(email: str) -> tuple[User, dict]:
    """Helper to create or retrieve test user and valid auth headers."""
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


def _cleanup_test_user_data(user_id: int):
    """Clean up WS-1 and WS-2 records for a user between tests."""
    db = SessionLocal()
    try:
        db.query(EmergencyEvent).filter(EmergencyEvent.user_id == user_id).delete()
        db.query(TrustedContact).filter(TrustedContact.user_id == user_id).delete()
        db.query(EmergencyProfile).filter(EmergencyProfile.user_id == user_id).delete()
        db.commit()
    finally:
        db.close()


def _setup_complete_ws1_profile(user_id: int, headers: dict):
    """Helper to configure a complete WS-1 profile for a test user."""
    _cleanup_test_user_data(user_id)
    # 1. Profile with mobile & consent
    client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9876543210",
        "emergency_email": "complete_user@test.com",
        "location_sharing_consent": True,
    }, headers=headers)
    # 2. Add 2 trusted contacts
    client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Contact One",
        "relationship": "Parent",
        "mobile_number": "9811122233",
    }, headers=headers)
    client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Contact Two",
        "relationship": "Friend",
        "mobile_number": "9844455566",
    }, headers=headers)


# ═════════════════════════════════════════════════════════════════════════════
# WS-1 TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_01_emergency_profile_creation_and_consent_default():
    """WS-1: Test creating emergency profile and verifying location_sharing_consent defaults to False."""
    user, headers = _create_test_user("ws1_user_a@naviscape.test")
    _cleanup_test_user_data(user.id)

    res_get = client.get("/api/women-safety/emergency-profile", headers=headers)
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["emergency_profile"] is None
    assert data_get["location_sharing_consent"] is False
    assert data_get["profile_complete"] is False
    assert data_get["contacts_count"] == 0

    payload = {
        "emergency_mobile": "9876543210",
        "emergency_email": "emergency_a@example.com",
    }
    res_put = client.put("/api/women-safety/emergency-profile", json=payload, headers=headers)
    assert res_put.status_code == 200
    data = res_put.json()
    assert data["emergency_profile"] is not None
    assert data["emergency_profile"]["emergency_mobile"] == "9876543210"
    assert data["emergency_profile"]["emergency_email"] == "emergency_a@example.com"
    assert data["emergency_profile"]["location_sharing_consent"] is False
    assert data["location_sharing_consent"] is False
    assert data["profile_complete"] is False


def test_02_emergency_profile_retrieval():
    """WS-1: Test retrieving authenticated user's emergency profile."""
    user, headers = _create_test_user("ws1_user_a@naviscape.test")
    res = client.get("/api/women-safety/emergency-profile", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["emergency_profile"]["user_id"] == user.id
    assert data["emergency_profile"]["emergency_mobile"] == "9876543210"


def test_03_emergency_profile_update_and_consent_enablement():
    """WS-1: Test updating profile and explicitly enabling location sharing consent."""
    user, headers = _create_test_user("ws1_user_a@naviscape.test")
    payload = {
        "emergency_mobile": "9123456780",
        "emergency_email": "updated_a@example.com",
        "location_sharing_consent": True,
    }
    res = client.put("/api/women-safety/emergency-profile", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["emergency_profile"]["emergency_mobile"] == "9123456780"
    assert data["emergency_profile"]["emergency_email"] == "updated_a@example.com"
    assert data["emergency_profile"]["location_sharing_consent"] is True
    assert data["location_sharing_consent"] is True


def test_04_trusted_contact_creation():
    """WS-1: Test adding trusted contacts."""
    user, headers = _create_test_user("ws1_user_a@naviscape.test")
    contact1 = {
        "contact_name": "Aarav Sharma",
        "relationship": "Brother",
        "mobile_number": "9811122233",
        "email": "aarav@family.test",
    }
    res1 = client.post("/api/women-safety/trusted-contacts", json=contact1, headers=headers)
    assert res1.status_code == 201
    d1 = res1.json()
    assert d1["contact_name"] == "Aarav Sharma"
    assert d1["relationship"] == "Brother"
    assert d1["mobile_number"] == "9811122233"
    assert d1["user_id"] == user.id

    contact2 = {
        "contact_name": "Priya Sharma",
        "relationship": "Mother",
        "mobile_number": "9844455566",
        "email": "priya@family.test",
    }
    res2 = client.post("/api/women-safety/trusted-contacts", json=contact2, headers=headers)
    assert res2.status_code == 201


def test_05_max_4_contacts_enforcement():
    """WS-1: Test that a user can have at most 4 trusted contacts; 5th attempt fails."""
    user, headers = _create_test_user("ws1_user_a@naviscape.test")
    res3 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Contact Three",
        "relationship": "Friend",
        "mobile_number": "9877788899",
    }, headers=headers)
    assert res3.status_code == 201

    res4 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Contact Four",
        "relationship": "Colleague",
        "mobile_number": "9866655544",
    }, headers=headers)
    assert res4.status_code == 201

    res5 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Contact Five",
        "relationship": "Neighbor",
        "mobile_number": "9811100022",
    }, headers=headers)
    assert res5.status_code == 400
    assert "Maximum limit of 4" in res5.json()["detail"]


def test_06_trusted_contact_update():
    """WS-1: Test updating an existing trusted contact."""
    user, headers = _create_test_user("ws1_user_a@naviscape.test")
    res_get = client.get("/api/women-safety/emergency-profile", headers=headers)
    contacts = res_get.json()["trusted_contacts"]
    first_contact = contacts[0]

    update_payload = {
        "contact_name": "Aarav Sharma Updated",
        "relationship": "Guardian",
        "mobile_number": "9999888877",
    }
    res_up = client.put(
        f"/api/women-safety/trusted-contacts/{first_contact['id']}",
        json=update_payload,
        headers=headers,
    )
    assert res_up.status_code == 200
    updated_data = res_up.json()
    assert updated_data["contact_name"] == "Aarav Sharma Updated"
    assert updated_data["relationship"] == "Guardian"
    assert updated_data["mobile_number"] == "9999888877"


def test_07_trusted_contact_deletion():
    """WS-1: Test deleting a trusted contact."""
    user, headers = _create_test_user("ws1_user_a@naviscape.test")
    res_get = client.get("/api/women-safety/emergency-profile", headers=headers)
    contacts = res_get.json()["trusted_contacts"]
    contact_to_delete = contacts[-1]

    res_del = client.delete(f"/api/women-safety/trusted-contacts/{contact_to_delete['id']}", headers=headers)
    assert res_del.status_code == 200
    assert "deleted successfully" in res_del.json()["message"]

    res_after = client.get("/api/women-safety/emergency-profile", headers=headers)
    assert res_after.json()["contacts_count"] == 3


def test_08_minimum_2_contacts_completion_logic():
    """WS-1: Test profile_complete condition."""
    user, headers = _create_test_user("ws1_completion_test@naviscape.test")
    _cleanup_test_user_data(user.id)

    r1 = client.get("/api/women-safety/emergency-profile", headers=headers)
    assert r1.json()["profile_complete"] is False

    client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9876543210",
        "location_sharing_consent": False,
    }, headers=headers)
    r2 = client.get("/api/women-safety/emergency-profile", headers=headers)
    assert r2.json()["profile_complete"] is False

    client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9876543210",
        "location_sharing_consent": True,
    }, headers=headers)
    r3 = client.get("/api/women-safety/emergency-profile", headers=headers)
    assert r3.json()["profile_complete"] is False

    c1_res = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Contact 1",
        "relationship": "Friend",
        "mobile_number": "9812345678",
    }, headers=headers)
    assert c1_res.status_code == 201
    r4 = client.get("/api/women-safety/emergency-profile", headers=headers)
    assert r4.json()["contacts_count"] == 1
    assert r4.json()["profile_complete"] is False

    c2_res = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Contact 2",
        "relationship": "Sister",
        "mobile_number": "9887654321",
    }, headers=headers)
    assert c2_res.status_code == 201
    r5 = client.get("/api/women-safety/emergency-profile", headers=headers)
    assert r5.json()["contacts_count"] == 2
    assert r5.json()["profile_complete"] is True


def test_11_to_14_multitenant_ownership_isolation():
    """WS-1: Verify multi-tenant isolation."""
    user_a, headers_a = _create_test_user("ws1_alice@naviscape.test")
    user_b, headers_b = _create_test_user("ws1_bob@naviscape.test")
    _cleanup_test_user_data(user_a.id)
    _cleanup_test_user_data(user_b.id)

    client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9811111111",
        "emergency_email": "alice_em@test.com",
        "location_sharing_consent": True,
    }, headers=headers_a)
    c_alice = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Alice Contact",
        "relationship": "Mother",
        "mobile_number": "9822222222",
    }, headers=headers_a).json()

    client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9833333333",
        "emergency_email": "bob_em@test.com",
        "location_sharing_consent": False,
    }, headers=headers_b)
    c_bob = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Bob Contact",
        "relationship": "Father",
        "mobile_number": "9844444444",
    }, headers=headers_b).json()

    res_a_prof = client.get("/api/women-safety/emergency-profile", headers=headers_a).json()
    assert res_a_prof["emergency_profile"]["emergency_mobile"] == "9811111111"
    assert res_a_prof["emergency_profile"]["user_id"] == user_a.id

    contacts_a = [c["contact_name"] for c in res_a_prof["trusted_contacts"]]
    assert "Alice Contact" in contacts_a
    assert "Bob Contact" not in contacts_a

    res_hack_update = client.put(
        f"/api/women-safety/trusted-contacts/{c_bob['id']}",
        json={"contact_name": "Hacked Name", "relationship": "Hacked", "mobile_number": "9999999999"},
        headers=headers_a,
    )
    assert res_hack_update.status_code == 404

    res_hack_delete = client.delete(
        f"/api/women-safety/trusted-contacts/{c_bob['id']}",
        headers=headers_a,
    )
    assert res_hack_delete.status_code == 404


def test_15_invalid_phone_number_rejected():
    """WS-1: Test invalid Indian phone numbers."""
    user, headers = _create_test_user("ws1_val_test@naviscape.test")
    r1 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Invalid Phone",
        "relationship": "Friend",
        "mobile_number": "12345",
    }, headers=headers)
    assert r1.status_code in (400, 422)


def test_16_invalid_email_rejected():
    """WS-1: Test invalid emails."""
    user, headers = _create_test_user("ws1_val_test@naviscape.test")
    r = client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9876543210",
        "emergency_email": "not-an-email",
    }, headers=headers)
    assert r.status_code in (400, 422)


def test_17_existing_naviscape_data_isolation():
    """WS-1: Verify that existing database tables and records remain completely untouched."""
    from app.models.traffic import TrafficData, TrafficHourly, RouteHistory
    from app.models.police_station import PoliceStation
    from app.models.hospital import Hospital
    from app.models.accident import AccidentData
    from app.models.road_hazard import RoadHazard

    db = SessionLocal()
    try:
        assert db.query(TrafficData).count() >= 800
        assert db.query(TrafficHourly).count() >= 80
        assert db.query(PoliceStation).count() == 921
        assert db.query(Hospital).count() == 2226
        assert db.query(AccidentData).count() == 95723
        assert db.query(RouteHistory).count() >= 15
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# WS-2 TESTS: SOS TRIGGER & EMERGENCY EVENTS
# ═════════════════════════════════════════════════════════════════════════════

def test_ws2_sos_requires_authentication():
    """WS-2 Requirement 1: Unauthenticated requests to emergency endpoints must be rejected with 401."""
    res1 = client.post("/api/women-safety/emergency-events", json={"latitude": 12.9716, "longitude": 77.5946})
    assert res1.status_code == 401

    res2 = client.get("/api/women-safety/emergency-events/active")
    assert res2.status_code == 401

    res3 = client.post("/api/women-safety/emergency-events/1/cancel")
    assert res3.status_code == 401


def test_ws2_sos_requires_complete_women_safety_profile():
    """WS-2 Requirement 2: Incomplete profile cannot create emergency event (gated by WS-1 completeness)."""
    user, headers = _create_test_user("ws2_incomplete_user@naviscape.test")
    _cleanup_test_user_data(user.id)

    # 1. No profile, 0 contacts -> 400 Bad Request
    payload = {"latitude": 12.9716, "longitude": 77.5946, "location_accuracy_m": 10.5}
    res1 = client.post("/api/women-safety/emergency-events", json=payload, headers=headers)
    assert res1.status_code == 400
    assert "profile is incomplete" in res1.json()["detail"].lower()

    # 2. Add profile with consent=False -> Still 400
    client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9876543210",
        "location_sharing_consent": False,
    }, headers=headers)
    res2 = client.post("/api/women-safety/emergency-events", json=payload, headers=headers)
    assert res2.status_code == 400

    # 3. Enable consent (True), but only 1 contact -> Still 400
    client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9876543210",
        "location_sharing_consent": True,
    }, headers=headers)
    client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Single Contact",
        "relationship": "Friend",
        "mobile_number": "9812345678",
    }, headers=headers)
    res3 = client.post("/api/women-safety/emergency-events", json=payload, headers=headers)
    assert res3.status_code == 400
    assert "at least 2 trusted contacts" in res3.json()["detail"].lower()


def test_ws2_sos_valid_profile_creates_active_event():
    """WS-2 Requirement 3: Valid authenticated user with complete profile + valid GPS creates ACTIVE event."""
    user, headers = _create_test_user("ws2_complete_user@naviscape.test")
    _setup_complete_ws1_profile(user.id, headers)

    payload = {
        "latitude": 12.9716555,
        "longitude": 77.5946222,
        "location_accuracy_m": 8.5,
    }
    res = client.post("/api/women-safety/emergency-events", json=payload, headers=headers)
    assert res.status_code == 201
    event = res.json()
    assert event["id"] is not None
    assert event["user_id"] == user.id
    assert event["status"] == "ACTIVE"
    assert abs(event["latitude"] - 12.9716555) < 0.0001
    assert abs(event["longitude"] - 77.5946222) < 0.0001
    assert event["location_accuracy_m"] == 8.5
    assert event["triggered_at"] is not None
    assert event["cancelled_at"] is None


def test_ws2_sos_invalid_latitude_rejected():
    """WS-2 Requirement 4: Latitude must be between -90 and 90, non-NaN, non-Inf."""
    user, headers = _create_test_user("ws2_complete_user@naviscape.test")

    # Lat > 90
    r1 = client.post("/api/women-safety/emergency-events", json={"latitude": 91.0, "longitude": 77.5946}, headers=headers)
    assert r1.status_code in (400, 422)

    # Lat < -90
    r2 = client.post("/api/women-safety/emergency-events", json={"latitude": -95.0, "longitude": 77.5946}, headers=headers)
    assert r2.status_code in (400, 422)


def test_ws2_sos_invalid_longitude_rejected():
    """WS-2 Requirement 5: Longitude must be between -180 and 180, non-NaN, non-Inf."""
    user, headers = _create_test_user("ws2_complete_user@naviscape.test")

    # Lng > 180
    r1 = client.post("/api/women-safety/emergency-events", json={"latitude": 12.9716, "longitude": 185.0}, headers=headers)
    assert r1.status_code in (400, 422)

    # Lng < -180
    r2 = client.post("/api/women-safety/emergency-events", json={"latitude": 12.9716, "longitude": -195.0}, headers=headers)
    assert r2.status_code in (400, 422)


def test_ws2_sos_missing_coordinates_rejected():
    """WS-2 Requirement 6: Missing coordinates in payload are strictly rejected."""
    user, headers = _create_test_user("ws2_complete_user@naviscape.test")

    r1 = client.post("/api/women-safety/emergency-events", json={}, headers=headers)
    assert r1.status_code in (400, 422)

    r2 = client.post("/api/women-safety/emergency-events", json={"latitude": 12.9716}, headers=headers)
    assert r2.status_code in (400, 422)


def test_ws2_sos_no_fake_location_fallback():
    """WS-2 Requirement 7: Missing/invalid GPS coordinates must never fall back to Bangalore Center."""
    user, headers = _create_test_user("ws2_complete_user@naviscape.test")

    r_none = client.post("/api/women-safety/emergency-events", json={"latitude": None, "longitude": None}, headers=headers)
    assert r_none.status_code in (400, 422)


def test_ws2_active_event_retrieval():
    """WS-2 Requirement 8: User can retrieve own active emergency event."""
    user, headers = _create_test_user("ws2_complete_user@naviscape.test")

    res = client.get("/api/women-safety/emergency-events/active", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["has_active_event"] is True
    assert data["event"]["status"] == "ACTIVE"
    assert data["event"]["user_id"] == user.id


def test_ws2_user_isolation():
    """WS-2 Requirement 9: User A cannot retrieve User B's emergency event."""
    user_a, headers_a = _create_test_user("ws2_user_a@naviscape.test")
    user_b, headers_b = _create_test_user("ws2_user_b@naviscape.test")

    _setup_complete_ws1_profile(user_a.id, headers_a)
    _setup_complete_ws1_profile(user_b.id, headers_b)

    # User A creates emergency event
    res_a = client.post("/api/women-safety/emergency-events", json={
        "latitude": 12.9111,
        "longitude": 77.5222,
        "location_accuracy_m": 5.0,
    }, headers=headers_a)
    assert res_a.status_code == 201
    event_a = res_a.json()

    # User B queries active event -> User B has NO active event
    res_b_active = client.get("/api/women-safety/emergency-events/active", headers=headers_b)
    assert res_b_active.status_code == 200
    assert res_b_active.json()["has_active_event"] is False
    assert res_b_active.json()["event"] is None


def test_ws2_user_cannot_cancel_other_user_event():
    """WS-2 Requirement 10: User A cannot cancel User B's emergency event (404)."""
    user_a, headers_a = _create_test_user("ws2_user_a@naviscape.test")
    user_b, headers_b = _create_test_user("ws2_user_b@naviscape.test")

    # User B gets active event ID from User A's session
    active_a = client.get("/api/women-safety/emergency-events/active", headers=headers_a).json()["event"]
    assert active_a is not None

    # User B attempts to cancel User A's event -> 404 Not Found
    res_hack = client.post(f"/api/women-safety/emergency-events/{active_a['id']}/cancel", headers=headers_b)
    assert res_hack.status_code == 404
    assert "not found" in res_hack.json()["detail"].lower()


def test_ws2_active_to_cancelled_transition():
    """WS-2 Requirement 11: ACTIVE -> CANCELLED transition sets status and cancelled_at timestamp."""
    user_a, headers_a = _create_test_user("ws2_user_a@naviscape.test")

    active_a = client.get("/api/women-safety/emergency-events/active", headers=headers_a).json()["event"]
    assert active_a is not None

    res_cancel = client.post(f"/api/women-safety/emergency-events/{active_a['id']}/cancel", headers=headers_a)
    assert res_cancel.status_code == 200
    cancelled_event = res_cancel.json()
    assert cancelled_event["status"] == "CANCELLED"
    assert cancelled_event["cancelled_at"] is not None

    # Active endpoint now returns has_active_event = False
    res_active_now = client.get("/api/women-safety/emergency-events/active", headers=headers_a)
    assert res_active_now.json()["has_active_event"] is False


def test_ws2_cancel_preserves_event_record():
    """WS-2 Requirement 12: Cancellation does NOT delete the emergency event from the database."""
    db = SessionLocal()
    try:
        user_a, _ = _create_test_user("ws2_user_a@naviscape.test")
        events = db.query(EmergencyEvent).filter(EmergencyEvent.user_id == user_a.id).all()
        assert len(events) >= 1
        for ev in events:
            assert ev.status in ("ACTIVE", "CANCELLED")
    finally:
        db.close()


def test_ws2_cancel_idempotency():
    """WS-2 Requirement 13: Cancelling an already CANCELLED event behaves safely and idempotently."""
    user_a, headers_a = _create_test_user("ws2_user_a@naviscape.test")

    db = SessionLocal()
    try:
        ev = db.query(EmergencyEvent).filter(EmergencyEvent.user_id == user_a.id, EmergencyEvent.status == "CANCELLED").first()
        assert ev is not None
        ev_id = ev.id
    finally:
        db.close()

    res_repeat = client.post(f"/api/women-safety/emergency-events/{ev_id}/cancel", headers=headers_a)
    assert res_repeat.status_code == 200
    assert res_repeat.json()["status"] == "CANCELLED"


def test_ws2_duplicate_active_event_prevention():
    """WS-2 Requirement 14: Enforces at most one ACTIVE emergency event per user."""
    user_a, headers_a = _create_test_user("ws2_user_a@naviscape.test")
    _cleanup_test_user_data(user_a.id)
    _setup_complete_ws1_profile(user_a.id, headers_a)

    # 1. Create first active event -> 201 Created
    r1 = client.post("/api/women-safety/emergency-events", json={"latitude": 12.9716, "longitude": 77.5946}, headers=headers_a)
    assert r1.status_code == 201

    # 2. Attempt to create second active event -> 409 Conflict
    r2 = client.post("/api/women-safety/emergency-events", json={"latitude": 12.9800, "longitude": 77.6000}, headers=headers_a)
    assert r2.status_code == 409
    assert "already in progress" in r2.json()["detail"].lower()


def test_ws2_existing_database_isolation():
    """WS-2 Requirement 15: Existing NAVISCAPE database records remain untouched."""
    from app.models.traffic import TrafficData, TrafficHourly, RouteHistory
    from app.models.police_station import PoliceStation
    from app.models.hospital import Hospital
    from app.models.accident import AccidentData

    db = SessionLocal()
    try:
        assert db.query(TrafficData).count() >= 800
        assert db.query(TrafficHourly).count() >= 80
        assert db.query(PoliceStation).count() == 921
        assert db.query(Hospital).count() == 2226
        assert db.query(AccidentData).count() == 95723
        assert db.query(RouteHistory).count() >= 15
    finally:
        db.close()


def test_ws2_existing_ws1_functionality():
    """WS-2 Requirement 16: WS-1 profile and trusted contacts continue to work seamlessly."""
    user, headers = _create_test_user("ws2_ws1_compat@naviscape.test")
    _setup_complete_ws1_profile(user.id, headers)

    overview = client.get("/api/women-safety/emergency-profile", headers=headers).json()
    assert overview["profile_complete"] is True
    assert overview["contacts_count"] == 2
    assert overview["has_emergency_mobile"] is True
    assert overview["location_sharing_consent"] is True


if __name__ == "__main__":
    tests = [
        # WS-1
        ("WS-1 Profile Creation & Default Consent", test_01_emergency_profile_creation_and_consent_default),
        ("WS-1 Profile Retrieval", test_02_emergency_profile_retrieval),
        ("WS-1 Profile Update & Consent Enablement", test_03_emergency_profile_update_and_consent_enablement),
        ("WS-1 Trusted Contact Creation", test_04_trusted_contact_creation),
        ("WS-1 Max 4 Contacts Enforcement", test_05_max_4_contacts_enforcement),
        ("WS-1 Trusted Contact Update", test_06_trusted_contact_update),
        ("WS-1 Trusted Contact Deletion", test_07_trusted_contact_deletion),
        ("WS-1 Min 2 Contacts Completion Logic", test_08_minimum_2_contacts_completion_logic),
        ("WS-1 Multi-Tenant Ownership Isolation", test_11_to_14_multitenant_ownership_isolation),
        ("WS-1 Invalid Phone Numbers Rejected", test_15_invalid_phone_number_rejected),
        ("WS-1 Invalid Email Rejected", test_16_invalid_email_rejected),
        ("WS-1 Existing NAVISCAPE Data Isolation", test_17_existing_naviscape_data_isolation),

        # WS-2
        ("WS-2 SOS Requires Authentication", test_ws2_sos_requires_authentication),
        ("WS-2 SOS Requires Complete Profile Gate", test_ws2_sos_requires_complete_women_safety_profile),
        ("WS-2 Valid Profile Creates Active Event", test_ws2_sos_valid_profile_creates_active_event),
        ("WS-2 Invalid Latitude Rejected", test_ws2_sos_invalid_latitude_rejected),
        ("WS-2 Invalid Longitude Rejected", test_ws2_sos_invalid_longitude_rejected),
        ("WS-2 Missing Coordinates Rejected", test_ws2_sos_missing_coordinates_rejected),
        ("WS-2 No Fake Location Fallback", test_ws2_sos_no_fake_location_fallback),
        ("WS-2 Active Event Retrieval", test_ws2_active_event_retrieval),
        ("WS-2 User Isolation", test_ws2_user_isolation),
        ("WS-2 User Cannot Cancel Other User Event", test_ws2_user_cannot_cancel_other_user_event),
        ("WS-2 Active to Cancelled Transition", test_ws2_active_to_cancelled_transition),
        ("WS-2 Cancel Preserves Event Record", test_ws2_cancel_preserves_event_record),
        ("WS-2 Cancel Idempotency", test_ws2_cancel_idempotency),
        ("WS-2 Duplicate Active Event Prevention", test_ws2_duplicate_active_event_prevention),
        ("WS-2 Existing Database Isolation", test_ws2_existing_database_isolation),
        ("WS-2 Existing WS-1 Functionality", test_ws2_existing_ws1_functionality),
    ]

    print(f"\nRunning Full Women Safety Test Suite ({len(tests)} tests)...")
    for name, fn in tests:
        fn()
        print(f"[PASS] {name}")
    print(f"\nALL {len(tests)} WOMEN SAFETY TEST CASES PASSED SUCCESSFULLY!")
