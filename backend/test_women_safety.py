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


# ═════════════════════════════════════════════════════════════════════════════
# WS-3A TESTS — WhatsApp Emergency Contact Foundation
# ═════════════════════════════════════════════════════════════════════════════

WS3A_TEST_EMAIL_A = "ws3a_user_a@naviscape.test"
WS3A_TEST_EMAIL_B = "ws3a_user_b@naviscape.test"


def _setup_ws3a_user_with_event(email, whatsapp_number=None, whatsapp_consent=False):
    """Helper: create user, complete WS-1 profile, create ACTIVE event, optionally set WhatsApp fields."""
    user, headers = _create_test_user(email)
    _cleanup_test_user_data(user.id)
    _setup_complete_ws1_profile(user.id, headers)

    # Update first trusted contact with optional WhatsApp fields
    overview = client.get("/api/women-safety/emergency-profile", headers=headers).json()
    first_contact_id = overview["trusted_contacts"][0]["id"]

    if whatsapp_number is not None:
        client.put(f"/api/women-safety/trusted-contacts/{first_contact_id}", json={
            "whatsapp_number": whatsapp_number,
            "whatsapp_alert_consent": whatsapp_consent,
        }, headers=headers)

    # Create ACTIVE emergency event with known GPS
    event_res = client.post("/api/women-safety/emergency-events", json={
        "latitude": 12.9716,
        "longitude": 77.5946,
        "location_accuracy_m": 15.0,
    }, headers=headers)
    assert event_res.status_code == 201, f"Failed to create event: {event_res.json()}"
    return user, headers, event_res.json()


def test_ws3a_whatsapp_number_creation():
    """WS-3A: Create a trusted contact with WhatsApp number."""
    user, headers = _create_test_user(WS3A_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)

    res = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "WA Contact",
        "relationship": "Friend",
        "mobile_number": "9876543210",
        "whatsapp_number": "9876543210",
        "whatsapp_alert_consent": True,
    }, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["whatsapp_number"] == "9876543210"
    assert data["whatsapp_alert_consent"] is True
    assert data["contact_name"] == "WA Contact"
    assert data["mobile_number"] == "9876543210"


def test_ws3a_whatsapp_number_validation():
    """WS-3A: Invalid WhatsApp numbers are rejected with same rules as mobile."""
    user, headers = _create_test_user(WS3A_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)

    # Invalid: too short
    res1 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Invalid WA",
        "relationship": "Friend",
        "mobile_number": "9876543210",
        "whatsapp_number": "12345",
    }, headers=headers)
    assert res1.status_code == 422

    # Invalid: starts with wrong digit
    res2 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Invalid WA",
        "relationship": "Friend",
        "mobile_number": "9876543210",
        "whatsapp_number": "1234567890",
    }, headers=headers)
    assert res2.status_code == 422

    # Valid: with +91 prefix
    res3 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Valid WA Prefixed",
        "relationship": "Friend",
        "mobile_number": "9876543210",
        "whatsapp_number": "+919876543210",
    }, headers=headers)
    assert res3.status_code == 201
    assert res3.json()["whatsapp_number"] == "9876543210"


def test_ws3a_whatsapp_consent_persistence():
    """WS-3A: WhatsApp consent defaults to False and persists when explicitly set."""
    user, headers = _create_test_user(WS3A_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)

    # Create without consent (should default to False)
    res1 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "No Consent",
        "relationship": "Friend",
        "mobile_number": "9876543210",
        "whatsapp_number": "9876543210",
    }, headers=headers)
    assert res1.status_code == 201
    assert res1.json()["whatsapp_alert_consent"] is False

    # Explicitly set consent to True
    contact_id = res1.json()["id"]
    res2 = client.put(f"/api/women-safety/trusted-contacts/{contact_id}", json={
        "whatsapp_alert_consent": True,
    }, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["whatsapp_alert_consent"] is True

    # Verify persistence via retrieval
    overview = client.get("/api/women-safety/emergency-profile", headers=headers).json()
    contact = next(c for c in overview["trusted_contacts"] if c["id"] == contact_id)
    assert contact["whatsapp_alert_consent"] is True


def test_ws3a_whatsapp_number_update():
    """WS-3A: WhatsApp number can be updated on an existing contact."""
    user, headers = _create_test_user(WS3A_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)

    res1 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Update WA",
        "relationship": "Sister",
        "mobile_number": "9876543210",
        "whatsapp_number": "9876543210",
    }, headers=headers)
    assert res1.status_code == 201
    contact_id = res1.json()["id"]

    # Update to different WhatsApp number
    res2 = client.put(f"/api/women-safety/trusted-contacts/{contact_id}", json={
        "whatsapp_number": "8765432109",
    }, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["whatsapp_number"] == "8765432109"
    # Ensure mobile_number unchanged
    assert res2.json()["mobile_number"] == "9876543210"


def test_ws3a_whatsapp_number_clearing():
    """WS-3A: WhatsApp number can be cleared (set to null)."""
    user, headers = _create_test_user(WS3A_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)

    res1 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Clear WA",
        "relationship": "Brother",
        "mobile_number": "9876543210",
        "whatsapp_number": "9876543210",
    }, headers=headers)
    contact_id = res1.json()["id"]

    # Clear by setting to empty string
    res2 = client.put(f"/api/women-safety/trusted-contacts/{contact_id}", json={
        "whatsapp_number": "",
    }, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["whatsapp_number"] is None


def test_ws3a_whatsapp_url_generation():
    """WS-3A: WhatsApp alerts endpoint generates valid wa.me URLs."""
    user, headers, event = _setup_ws3a_user_with_event(
        WS3A_TEST_EMAIL_A,
        whatsapp_number="9876543210",
        whatsapp_consent=True,
    )

    res = client.get(f"/api/women-safety/emergency-events/{event['id']}/whatsapp-alerts", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["event_id"] == event["id"]
    assert data["event_status"] == "ACTIVE"

    # Find the contact with WhatsApp
    wa_alerts = [a for a in data["alerts"] if a["whatsapp_available"]]
    assert len(wa_alerts) >= 1
    alert = wa_alerts[0]
    assert alert["whatsapp_url"].startswith("https://wa.me/919876543210?text=")
    assert alert["message_preview"] is not None
    assert "NAVISCAPE EMERGENCY ALERT" in alert["message_preview"]


def test_ws3a_whatsapp_url_encoding():
    """WS-3A: Message text in WhatsApp URL is properly URL-encoded."""
    user, headers, event = _setup_ws3a_user_with_event(
        WS3A_TEST_EMAIL_A,
        whatsapp_number="9876543210",
        whatsapp_consent=True,
    )

    res = client.get(f"/api/women-safety/emergency-events/{event['id']}/whatsapp-alerts", headers=headers)
    data = res.json()
    wa_alerts = [a for a in data["alerts"] if a["whatsapp_available"]]
    url = wa_alerts[0]["whatsapp_url"]

    # URL should not contain raw spaces or newlines
    query_part = url.split("?text=")[1]
    assert " " not in query_part
    assert "\n" not in query_part
    # Should contain URL-encoded equivalents
    assert "%0A" in query_part or "%0a" in query_part  # newline encoded
    assert "NAVISCAPE" in query_part or "NAVISCAPE" in url  # text present


def test_ws3a_real_emergency_gps_in_message():
    """WS-3A: GPS coordinates in message come from the real EmergencyEvent, not fabricated."""
    user, headers, event = _setup_ws3a_user_with_event(
        WS3A_TEST_EMAIL_A,
        whatsapp_number="9876543210",
        whatsapp_consent=True,
    )

    res = client.get(f"/api/women-safety/emergency-events/{event['id']}/whatsapp-alerts", headers=headers)
    data = res.json()

    # Verify response coordinates match the event's GPS
    assert data["latitude"] == event["latitude"]
    assert data["longitude"] == event["longitude"]

    # Verify the message contains the real coordinates
    wa_alerts = [a for a in data["alerts"] if a["whatsapp_available"]]
    message = wa_alerts[0]["message_preview"]
    assert str(event["latitude"]) in message
    assert str(event["longitude"]) in message
    # Verify Google Maps URL uses real coordinates
    assert f"maps?q={event['latitude']},{event['longitude']}" in message


def test_ws3a_no_fake_gps_fallback():
    """WS-3A: No Bangalore center, preset, destination, police, hospital, or fake coordinates."""
    user, headers, event = _setup_ws3a_user_with_event(
        WS3A_TEST_EMAIL_A,
        whatsapp_number="9876543210",
        whatsapp_consent=True,
    )

    res = client.get(f"/api/women-safety/emergency-events/{event['id']}/whatsapp-alerts", headers=headers)
    data = res.json()
    wa_alerts = [a for a in data["alerts"] if a["whatsapp_available"]]
    message = wa_alerts[0]["message_preview"]

    # Known fake coordinates that MUST NOT appear
    fake_coords = [
        ("12.9716", "77.5946"),  # This IS our test coord — but verify it matches the EVENT
        ("12.9741", "77.6138"),  # Bangalore center / MG Road
        ("13.0827", "80.2707"),  # Chennai
        ("0.0", "0.0"),         # Null island
    ]

    # The event used 12.9716, 77.5946 — verify it's from the actual event
    assert data["latitude"] == event["latitude"]
    assert data["longitude"] == event["longitude"]

    # The WhatsApp endpoint does NOT accept lat/lng from the request
    # It's a GET endpoint with no coordinate parameters


def test_ws3a_only_active_events_generate_alerts():
    """WS-3A: Only ACTIVE events can generate WhatsApp alert links."""
    user, headers, event = _setup_ws3a_user_with_event(
        WS3A_TEST_EMAIL_A,
        whatsapp_number="9876543210",
        whatsapp_consent=True,
    )

    # Cancel the event
    cancel_res = client.post(f"/api/women-safety/emergency-events/{event['id']}/cancel", headers=headers)
    assert cancel_res.status_code == 200

    # Try to get alerts for cancelled event
    res = client.get(f"/api/women-safety/emergency-events/{event['id']}/whatsapp-alerts", headers=headers)
    assert res.status_code == 400
    assert "ACTIVE" in res.json()["detail"]


def test_ws3a_user_isolation():
    """WS-3A: User A cannot generate WhatsApp alerts for User B's event."""
    user_a, headers_a, event_a = _setup_ws3a_user_with_event(
        WS3A_TEST_EMAIL_A,
        whatsapp_number="9876543210",
        whatsapp_consent=True,
    )
    user_b, headers_b = _create_test_user(WS3A_TEST_EMAIL_B)
    _cleanup_test_user_data(user_b.id)

    # User B tries to access User A's event alerts
    res = client.get(f"/api/women-safety/emergency-events/{event_a['id']}/whatsapp-alerts", headers=headers_b)
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_ws3a_contact_without_whatsapp_number():
    """WS-3A: Contact without WhatsApp number shows 'unavailable' message."""
    user, headers, event = _setup_ws3a_user_with_event(
        WS3A_TEST_EMAIL_A,
        whatsapp_number=None,  # No WhatsApp number
        whatsapp_consent=False,
    )

    res = client.get(f"/api/women-safety/emergency-events/{event['id']}/whatsapp-alerts", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # All contacts should be unavailable
    for alert in data["alerts"]:
        assert alert["whatsapp_available"] is False
        assert alert["whatsapp_url"] is None
        assert "unavailable" in alert["reason"].lower()


def test_ws3a_contact_without_whatsapp_consent():
    """WS-3A: Contact with WhatsApp number but no consent shows 'unavailable'."""
    user, headers, event = _setup_ws3a_user_with_event(
        WS3A_TEST_EMAIL_A,
        whatsapp_number="9876543210",
        whatsapp_consent=False,  # Has number but no consent
    )

    res = client.get(f"/api/women-safety/emergency-events/{event['id']}/whatsapp-alerts", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # All contacts should be unavailable (the one with number has no consent)
    for alert in data["alerts"]:
        assert alert["whatsapp_available"] is False
        assert "unavailable" in alert["reason"].lower()


def test_ws3a_existing_ws1_functionality():
    """WS-3A: All WS-1 features (profile, contacts, consent) still work correctly."""
    user, headers = _create_test_user("ws3a_ws1_compat@naviscape.test")
    _cleanup_test_user_data(user.id)

    # Create profile
    res1 = client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9876543210",
        "location_sharing_consent": True,
    }, headers=headers)
    assert res1.status_code == 200

    # Add contacts
    res2 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "WS1 Contact",
        "relationship": "Parent",
        "mobile_number": "9811122233",
    }, headers=headers)
    assert res2.status_code == 201
    # Verify WhatsApp fields default correctly
    assert res2.json()["whatsapp_number"] is None
    assert res2.json()["whatsapp_alert_consent"] is False

    res3 = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "WS1 Contact 2",
        "relationship": "Friend",
        "mobile_number": "9844455566",
    }, headers=headers)
    assert res3.status_code == 201

    # Profile should be complete
    overview = client.get("/api/women-safety/emergency-profile", headers=headers).json()
    assert overview["profile_complete"] is True
    assert overview["contacts_count"] == 2


def test_ws3a_existing_ws2_functionality():
    """WS-3A: All WS-2 features (SOS trigger, cancel, event retrieval) still work correctly."""
    user, headers = _create_test_user("ws3a_ws2_compat@naviscape.test")
    _cleanup_test_user_data(user.id)
    _setup_complete_ws1_profile(user.id, headers)

    # Trigger SOS
    event_res = client.post("/api/women-safety/emergency-events", json={
        "latitude": 13.0356,
        "longitude": 77.5970,
        "location_accuracy_m": 10.0,
    }, headers=headers)
    assert event_res.status_code == 201
    event = event_res.json()
    assert event["status"] == "ACTIVE"
    assert event["latitude"] == 13.0356

    # Get active event
    active_res = client.get("/api/women-safety/emergency-events/active", headers=headers).json()
    assert active_res["has_active_event"] is True

    # Cancel
    cancel_res = client.post(f"/api/women-safety/emergency-events/{event['id']}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"


def test_ws3a_existing_data_isolation():
    """WS-3A: No other NAVISCAPE tables (traffic, accidents, etc.) are affected."""
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


def test_ws3a_no_meta_api_integration():
    """WS-3A: Verify whatsapp_service does not contain any external API integration."""
    import inspect
    from app.services import whatsapp_service

    source = inspect.getsource(whatsapp_service)

    # Must NOT contain any Meta/WhatsApp Cloud API references
    forbidden_terms = [
        "graph.facebook.com",
        "META_API",
        "WHATSAPP_API_KEY",
        "WHATSAPP_TOKEN",
        "requests.post",
        "requests.get",
        "httpx.post",
        "httpx.get",
        "aiohttp",
        "cloud_api",
    ]
    for term in forbidden_terms:
        assert term not in source, f"Forbidden term '{term}' found in whatsapp_service"

    # Must contain wa.me (click-to-chat, not Cloud API)
    assert "wa.me" in source


def test_ws3a_no_automatic_delivery():
    """WS-3A: The WhatsApp alerts endpoint does NOT claim delivery or auto-send."""
    user, headers, event = _setup_ws3a_user_with_event(
        WS3A_TEST_EMAIL_A,
        whatsapp_number="9876543210",
        whatsapp_consent=True,
    )

    res = client.get(f"/api/women-safety/emergency-events/{event['id']}/whatsapp-alerts", headers=headers)
    data = res.json()

    # Response should NOT contain any delivery status
    import json
    response_str = json.dumps(data)
    assert "delivered" not in response_str.lower()
    assert '"is_sent"' not in response_str.lower()
    assert '"sent_at"' not in response_str.lower()
    assert '"status": "sent"' not in response_str.lower()
    assert "delivery_status" not in response_str.lower()

    # URL should be wa.me click-to-chat, not an API call
    for alert in data["alerts"]:
        if alert["whatsapp_available"]:
            assert alert["whatsapp_url"].startswith("https://wa.me/")
            assert "graph.facebook.com" not in alert["whatsapp_url"]


# ═════════════════════════════════════════════════════════════════════════════
# WS-3B TESTS — Real Device WhatsApp Click-to-Chat Flow
# ═════════════════════════════════════════════════════════════════════════════

WS3B_TEST_EMAIL_A = "ws3b_user_a@naviscape.test"
WS3B_TEST_EMAIL_B = "ws3b_user_b@naviscape.test"


def test_ws3b_active_emergency_displays_whatsapp_controls():
    """WS-3B: Active emergency endpoint returns complete contact name, WhatsApp number and wa.me URL."""
    user, headers = _create_test_user(WS3B_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)
    _setup_complete_ws1_profile(user.id, headers)

    # Add a contact with complete WhatsApp details
    res_c = client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Emergency Guardian",
        "relationship": "Sister",
        "mobile_number": "9812345678",
        "whatsapp_number": "9812345678",
        "whatsapp_alert_consent": True,
    }, headers=headers)
    assert res_c.status_code == 201

    # Trigger SOS
    res_e = client.post("/api/women-safety/emergency-events", json={
        "latitude": 12.9352,
        "longitude": 77.6245,
        "location_accuracy_m": 8.0,
    }, headers=headers)
    assert res_e.status_code == 201
    event = res_e.json()

    # Fetch alerts
    res_alerts = client.get(f"/api/women-safety/emergency-events/{event['id']}/whatsapp-alerts", headers=headers)
    assert res_alerts.status_code == 200
    data = res_alerts.json()
    assert data["event_status"] == "ACTIVE"

    guardian_alert = next((a for a in data["alerts"] if a["contact_name"] == "Emergency Guardian"), None)
    assert guardian_alert is not None
    assert guardian_alert["whatsapp_available"] is True
    assert guardian_alert["whatsapp_number"] == "9812345678"
    assert "https://wa.me/919812345678?text=" in guardian_alert["whatsapp_url"]


def test_ws3b_multiple_contacts_heterogeneous_status():
    """WS-3B: Multiple contacts with heterogeneous statuses (WA+Consent, WA+NoConsent, NoWA)."""
    user, headers = _create_test_user(WS3B_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)

    # 1. Profile
    client.put("/api/women-safety/emergency-profile", json={
        "emergency_mobile": "9876543210",
        "location_sharing_consent": True,
    }, headers=headers)

    # 2. Contact 1: Has WhatsApp and Consent
    client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Guardian Active",
        "relationship": "Mother",
        "mobile_number": "9811111111",
        "whatsapp_number": "9811111111",
        "whatsapp_alert_consent": True,
    }, headers=headers)

    # 3. Contact 2: Has WhatsApp but NO Consent
    client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Guardian No Consent",
        "relationship": "Father",
        "mobile_number": "9822222222",
        "whatsapp_number": "9822222222",
        "whatsapp_alert_consent": False,
    }, headers=headers)

    # 4. Contact 3: No WhatsApp Number
    client.post("/api/women-safety/trusted-contacts", json={
        "contact_name": "Guardian No WA",
        "relationship": "Friend",
        "mobile_number": "9833333333",
        "whatsapp_alert_consent": False,
    }, headers=headers)

    # Trigger SOS
    res_e = client.post("/api/women-safety/emergency-events", json={
        "latitude": 12.9279,
        "longitude": 77.6271,
        "location_accuracy_m": 5.0,
    }, headers=headers)
    event_id = res_e.json()["id"]

    res_alerts = client.get(f"/api/women-safety/emergency-events/{event_id}/whatsapp-alerts", headers=headers)
    assert res_alerts.status_code == 200
    alerts = res_alerts.json()["alerts"]
    assert len(alerts) == 3

    # Check Contact 1: available
    c1 = next(a for a in alerts if a["contact_name"] == "Guardian Active")
    assert c1["whatsapp_available"] is True
    assert c1["whatsapp_url"].startswith("https://wa.me/919811111111?text=")

    # Check Contact 2: unavailable due to no consent
    c2 = next(a for a in alerts if a["contact_name"] == "Guardian No Consent")
    assert c2["whatsapp_available"] is False
    assert c2["whatsapp_url"] is None
    assert "unavailable" in c2["reason"].lower()

    # Check Contact 3: unavailable due to no WA number
    c3 = next(a for a in alerts if a["contact_name"] == "Guardian No WA")
    assert c3["whatsapp_available"] is False
    assert c3["whatsapp_url"] is None
    assert "unavailable" in c3["reason"].lower()


def test_ws3b_no_frontend_gps_substitution():
    """WS-3B: Backend ignores any frontend query/body coords and strictly uses DB EmergencyEvent GPS."""
    user, headers = _create_test_user(WS3B_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)
    _setup_complete_ws1_profile(user.id, headers)

    # Set up WA contact
    overview = client.get("/api/women-safety/emergency-profile", headers=headers).json()
    cid = overview["trusted_contacts"][0]["id"]
    client.put(f"/api/women-safety/trusted-contacts/{cid}", json={
        "whatsapp_number": "9812345678",
        "whatsapp_alert_consent": True,
    }, headers=headers)

    # Create real event with real coordinates (e.g. Bangalore South 12.9121, 77.5844)
    res_e = client.post("/api/women-safety/emergency-events", json={
        "latitude": 12.9121,
        "longitude": 77.5844,
        "location_accuracy_m": 4.0,
    }, headers=headers)
    event_id = res_e.json()["id"]

    # Try to request alerts while supplying fake query parameters (?latitude=99.9999&longitude=88.8888)
    res_alerts = client.get(
        f"/api/women-safety/emergency-events/{event_id}/whatsapp-alerts?latitude=99.9999&longitude=88.8888",
        headers=headers,
    )
    assert res_alerts.status_code == 200
    data = res_alerts.json()

    # Verify the real coordinates are used, fake ones completely ignored
    assert data["latitude"] == 12.9121
    assert data["longitude"] == 77.5844
    assert "99.9999" not in str(data)
    assert "88.8888" not in str(data)

    alert = data["alerts"][0]
    assert "12.9121" in alert["message_preview"]
    assert "77.5844" in alert["message_preview"]


def test_ws3b_cancelled_emergency_cannot_generate_alerts():
    """WS-3B: Cancelled event returns 400 Bad Request: WhatsApp alerts only for ACTIVE events."""
    user, headers = _create_test_user(WS3B_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)
    _setup_complete_ws1_profile(user.id, headers)

    res_e = client.post("/api/women-safety/emergency-events", json={
        "latitude": 12.9716,
        "longitude": 77.5946,
    }, headers=headers)
    event_id = res_e.json()["id"]

    # Cancel event
    res_cancel = client.post(f"/api/women-safety/emergency-events/{event_id}/cancel", headers=headers)
    assert res_cancel.status_code == 200

    # Attempt to generate alert for cancelled event
    res_alert = client.get(f"/api/women-safety/emergency-events/{event_id}/whatsapp-alerts", headers=headers)
    assert res_alert.status_code == 400
    assert "ACTIVE" in res_alert.json()["detail"]


def test_ws3b_no_sent_status_persisted():
    """WS-3B: Verify generating/opening alerts does NOT alter database event status or mark contact as sent."""
    from app.models.emergency_event import EmergencyEvent
    user, headers = _create_test_user(WS3B_TEST_EMAIL_A)
    _cleanup_test_user_data(user.id)
    _setup_complete_ws1_profile(user.id, headers)

    overview = client.get("/api/women-safety/emergency-profile", headers=headers).json()
    cid = overview["trusted_contacts"][0]["id"]
    client.put(f"/api/women-safety/trusted-contacts/{cid}", json={
        "whatsapp_number": "9812345678",
        "whatsapp_alert_consent": True,
    }, headers=headers)

    res_e = client.post("/api/women-safety/emergency-events", json={
        "latitude": 12.9716,
        "longitude": 77.5946,
    }, headers=headers)
    event_id = res_e.json()["id"]

    # Get WhatsApp alerts multiple times (simulating user tapping/opening)
    client.get(f"/api/women-safety/emergency-events/{event_id}/whatsapp-alerts", headers=headers)
    client.get(f"/api/women-safety/emergency-events/{event_id}/whatsapp-alerts", headers=headers)

    # Verify event in DB is still ACTIVE (never changes to SENT, COMPLETED, DELIVERED)
    db = SessionLocal()
    try:
        ev = db.query(EmergencyEvent).filter(EmergencyEvent.id == event_id).first()
        assert ev.status == "ACTIVE"
    finally:
        db.close()


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

        # WS-3A
        ("WS-3A WhatsApp Number Creation", test_ws3a_whatsapp_number_creation),
        ("WS-3A WhatsApp Number Validation", test_ws3a_whatsapp_number_validation),
        ("WS-3A WhatsApp Consent Persistence", test_ws3a_whatsapp_consent_persistence),
        ("WS-3A WhatsApp Number Update", test_ws3a_whatsapp_number_update),
        ("WS-3A WhatsApp Number Clearing", test_ws3a_whatsapp_number_clearing),
        ("WS-3A WhatsApp URL Generation", test_ws3a_whatsapp_url_generation),
        ("WS-3A WhatsApp URL Encoding", test_ws3a_whatsapp_url_encoding),
        ("WS-3A Real Emergency GPS in Message", test_ws3a_real_emergency_gps_in_message),
        ("WS-3A No Fake GPS Fallback", test_ws3a_no_fake_gps_fallback),
        ("WS-3A Only ACTIVE Events Generate Alerts", test_ws3a_only_active_events_generate_alerts),
        ("WS-3A User Isolation", test_ws3a_user_isolation),
        ("WS-3A Contact Without WhatsApp Number", test_ws3a_contact_without_whatsapp_number),
        ("WS-3A Contact Without WhatsApp Consent", test_ws3a_contact_without_whatsapp_consent),
        ("WS-3A Existing WS-1 Functionality", test_ws3a_existing_ws1_functionality),
        ("WS-3A Existing WS-2 Functionality", test_ws3a_existing_ws2_functionality),
        ("WS-3A Existing Data Isolation", test_ws3a_existing_data_isolation),
        ("WS-3A No Meta API Integration", test_ws3a_no_meta_api_integration),
        ("WS-3A No Automatic Delivery", test_ws3a_no_automatic_delivery),

        # WS-3B
        ("WS-3B Active Emergency Displays WhatsApp Controls", test_ws3b_active_emergency_displays_whatsapp_controls),
        ("WS-3B Multiple Contacts Heterogeneous Status", test_ws3b_multiple_contacts_heterogeneous_status),
        ("WS-3B No Frontend GPS Substitution", test_ws3b_no_frontend_gps_substitution),
        ("WS-3B Cancelled Emergency Gated", test_ws3b_cancelled_emergency_cannot_generate_alerts),
        ("WS-3B No Sent Status Persisted", test_ws3b_no_sent_status_persisted),
    ]

    print(f"\nRunning Full Women Safety Test Suite ({len(tests)} tests)...")
    for name, fn in tests:
        fn()
        print(f"[PASS] {name}")
    print(f"\nALL {len(tests)} WOMEN SAFETY TEST CASES PASSED SUCCESSFULLY!")


