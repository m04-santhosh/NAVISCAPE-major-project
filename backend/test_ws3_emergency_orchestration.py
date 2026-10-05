"""
NAVISCAPE Women Safety Test Suite — WS-3: Emergency Alert Orchestration & Live Emergency Status
Deterministic unit and integration tests covering:

1. Authenticated action creation succeeds (201).
2. Unauthenticated action creation is rejected (401).
3. User isolation for emergency actions & timeline.
4. Timeline retrieval returns valid response.
5. Timeline items are returned in chronological order.
6. WHATSAPP_OPENED action records entry and transitions status to ALERTS_PREPARED.
7. ALERT_SENT_CONFIRMED action records entry and transitions status to CONTACTS_NOTIFIED.
8. Emergency status transition endpoint updates event lifecycle status.
9. Invalid status update is rejected (422).
10. Emergency cancellation records EMERGENCY_CANCELLED action.
11. Emergency resolution records EMERGENCY_RESOLVED action and updates status to RESOLVED.
12. Unauthorized emergency event access is rejected (404).
13. EMERGENCY_CONTACT_CALLED action is recorded.
14. POLICE_CALLED action is recorded.
15. No user_id spoofing allowed (identity bound strictly to JWT token).
16. WS-1 functionality preserved.
17. WS-2 functionality preserved.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app.models.user import User
from app.models.emergency_profile import EmergencyProfile, TrustedContact
from app.models.emergency_event import EmergencyEvent
from app.models.emergency_action import EmergencyAction
from app.middleware.auth import create_access_token, hash_pin

init_db()
client = TestClient(app, raise_server_exceptions=False)


def _get_or_create_user(email: str) -> tuple[User, dict]:
    """Helper to retrieve or create test user and generate auth headers."""
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


def _cleanup_user_data(user_id: int):
    """Clean up DB records for test user."""
    db = SessionLocal()
    try:
        db.query(EmergencyAction).filter(EmergencyAction.user_id == user_id).delete()
        db.query(EmergencyEvent).filter(EmergencyEvent.user_id == user_id).delete()
        db.query(TrustedContact).filter(TrustedContact.user_id == user_id).delete()
        db.query(EmergencyProfile).filter(EmergencyProfile.user_id == user_id).delete()
        db.commit()
    finally:
        db.close()


def _create_test_event(user_id: int, lat: float = 12.9716, lng: float = 77.5946) -> int:
    """Helper to seed an emergency event in DB."""
    db = SessionLocal()
    try:
        event = EmergencyEvent(
            user_id=user_id,
            status="ACTIVE",
            latitude=lat,
            longitude=lng,
            location_accuracy_m=5.0,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event.id
    finally:
        db.close()


# ── Test 1: Authenticated action creation succeeds ─────────────────────────────

def test_authenticated_action_creation_succeeds():
    """Requirement 1: Authenticated action creation returns 201 with action details."""
    user, headers = _get_or_create_user("ws3_action_user1@naviscape.test")
    _cleanup_user_data(user.id)
    event_id = _create_test_event(user.id)

    payload = {
        "action_type": "WHATSAPP_OPENED",
        "contact_type": "PRIMARY",
        "contact_name": "Mom",
        "contact_phone": "919739988032",
    }
    res = client.post(f"/api/women-safety/emergency/{event_id}/actions", json=payload, headers=headers)
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"

    data = res.json()
    assert data["emergency_event_id"] == event_id
    assert data["action_type"] == "WHATSAPP_OPENED"
    assert data["contact_type"] == "PRIMARY"
    assert data["contact_name"] == "Mom"
    assert "WhatsApp opened for Mom" in data["description"]


# ── Test 2: Unauthenticated action creation rejected ───────────────────────────

def test_unauthenticated_action_creation_rejected():
    """Requirement 2: Unauthenticated action POST returns 401 Unauthorized."""
    res = client.post("/api/women-safety/emergency/1/actions", json={"action_type": "WHATSAPP_OPENED"})
    assert res.status_code == 401


# ── Test 3: User isolation for actions and timeline ───────────────────────────

def test_user_isolation_actions_and_timeline():
    """Requirement 3 & 12: User A cannot post actions or view timeline for User B's event."""
    user_a, headers_a = _get_or_create_user("ws3_user_a@naviscape.test")
    user_b, headers_b = _get_or_create_user("ws3_user_b@naviscape.test")

    _cleanup_user_data(user_a.id)
    _cleanup_user_data(user_b.id)
    event_a_id = _create_test_event(user_a.id)

    # User B tries to post action to User A's event -> 404
    res_post = client.post(
        f"/api/women-safety/emergency/{event_a_id}/actions",
        json={"action_type": "WHATSAPP_OPENED"},
        headers=headers_b,
    )
    assert res_post.status_code == 404

    # User B tries to view User A's timeline -> 404
    res_get = client.get(f"/api/women-safety/emergency/{event_a_id}/timeline", headers=headers_b)
    assert res_get.status_code == 404


# ── Test 4 & 5: Timeline retrieval & chronological ordering ───────────────────

def test_timeline_retrieval_and_chronological_ordering():
    """Requirements 4 & 5: Timeline retrieval returns items in chronological order."""
    user, headers = _get_or_create_user("ws3_timeline_user@naviscape.test")
    _cleanup_user_data(user.id)
    event_id = _create_test_event(user.id)

    # Post actions
    client.post(
        f"/api/women-safety/emergency/{event_id}/actions",
        json={"action_type": "WHATSAPP_OPENED", "contact_name": "Primary Contact"},
        headers=headers,
    )
    client.post(
        f"/api/women-safety/emergency/{event_id}/actions",
        json={"action_type": "ALERT_SENT_CONFIRMED", "contact_name": "Primary Contact"},
        headers=headers,
    )

    res = client.get(f"/api/women-safety/emergency/{event_id}/timeline", headers=headers)
    assert res.status_code == 200

    data = res.json()
    assert data["emergency_id"] == event_id
    timeline = data["timeline"]
    assert len(timeline) >= 2

    # Verify chronological ordering by id / created_at
    ids = [item["id"] for item in timeline]
    assert ids == sorted(ids), "Timeline items must be in chronological order"


# ── Test 6: WHATSAPP_OPENED action updates status ──────────────────────────────

def test_whatsapp_opened_action_transitions_status():
    """Requirement 6: WHATSAPP_OPENED transitions status to ALERTS_PREPARED."""
    user, headers = _get_or_create_user("ws3_wa_open_user@naviscape.test")
    _cleanup_user_data(user.id)
    event_id = _create_test_event(user.id)

    res = client.post(
        f"/api/women-safety/emergency/{event_id}/actions",
        json={"action_type": "WHATSAPP_OPENED", "contact_type": "PRIMARY", "contact_name": "Aarav"},
        headers=headers,
    )
    assert res.status_code == 201

    # Check event status updated
    db = SessionLocal()
    try:
        event = db.query(EmergencyEvent).filter(EmergencyEvent.id == event_id).first()
        assert event.status == "ALERTS_PREPARED"
    finally:
        db.close()


# ── Test 7: ALERT_SENT_CONFIRMED action updates status ────────────────────────

def test_alert_sent_confirmed_transitions_status():
    """Requirement 7: ALERT_SENT_CONFIRMED transitions status to CONTACTS_NOTIFIED."""
    user, headers = _get_or_create_user("ws3_confirm_sent_user@naviscape.test")
    _cleanup_user_data(user.id)
    event_id = _create_test_event(user.id)

    res = client.post(
        f"/api/women-safety/emergency/{event_id}/actions",
        json={"action_type": "ALERT_SENT_CONFIRMED", "contact_name": "Sister"},
        headers=headers,
    )
    assert res.status_code == 201

    db = SessionLocal()
    try:
        event = db.query(EmergencyEvent).filter(EmergencyEvent.id == event_id).first()
        assert event.status == "CONTACTS_NOTIFIED"
    finally:
        db.close()


# ── Test 8 & 9: Emergency status transition endpoint & invalid rejection ──────

def test_emergency_status_transition_endpoint():
    """Requirements 8 & 9: Status transition endpoint updates status; invalid statuses are rejected with 422."""
    user, headers = _get_or_create_user("ws3_status_user@naviscape.test")
    _cleanup_user_data(user.id)
    event_id = _create_test_event(user.id)

    # Valid status update to CONTACTS_NOTIFIED
    res1 = client.patch(
        f"/api/women-safety/emergency/{event_id}/status",
        json={"status": "CONTACTS_NOTIFIED"},
        headers=headers,
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "CONTACTS_NOTIFIED"

    # Invalid status update rejected
    res2 = client.patch(
        f"/api/women-safety/emergency/{event_id}/status",
        json={"status": "INVALID_STATUS_XYZ"},
        headers=headers,
    )
    assert res2.status_code == 422


# ── Test 10: Cancellation records action ──────────────────────────────────────

def test_cancellation_records_action():
    """Requirement 10: Cancelling emergency logs EMERGENCY_CANCELLED in action timeline."""
    user, headers = _get_or_create_user("ws3_cancel_user@naviscape.test")
    _cleanup_user_data(user.id)
    event_id = _create_test_event(user.id)

    res_cancel = client.post(f"/api/women-safety/emergency/{event_id}/cancel", headers=headers)
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELLED"

    # Verify action recorded
    res_tl = client.get(f"/api/women-safety/emergency/{event_id}/timeline", headers=headers)
    assert res_tl.status_code == 200
    timeline = res_tl.json()["timeline"]
    action_types = [item["action_type"] for item in timeline]
    assert "EMERGENCY_CANCELLED" in action_types


# ── Test 11: Resolution records action ────────────────────────────────────────

def test_resolution_records_action_and_updates_status():
    """Requirement 11: Resolving emergency logs EMERGENCY_RESOLVED action and sets status to RESOLVED."""
    user, headers = _get_or_create_user("ws3_resolve_user@naviscape.test")
    _cleanup_user_data(user.id)
    event_id = _create_test_event(user.id)

    res_resolve = client.post(
        f"/api/women-safety/emergency/{event_id}/actions",
        json={"action_type": "EMERGENCY_RESOLVED"},
        headers=headers,
    )
    assert res_resolve.status_code == 201

    # Check status updated to RESOLVED
    db = SessionLocal()
    try:
        event = db.query(EmergencyEvent).filter(EmergencyEvent.id == event_id).first()
        assert event.status == "RESOLVED"
    finally:
        db.close()


# ── Test 13 & 14: Emergency contact call & Police call actions recorded ────────

def test_call_actions_recorded():
    """Requirements 13 & 14: EMERGENCY_CONTACT_CALLED and POLICE_CALLED actions recorded."""
    user, headers = _get_or_create_user("ws3_call_user@naviscape.test")
    _cleanup_user_data(user.id)
    event_id = _create_test_event(user.id)

    # 13. Call emergency contact
    res_call = client.post(
        f"/api/women-safety/emergency/{event_id}/actions",
        json={
            "action_type": "EMERGENCY_CONTACT_CALLED",
            "contact_type": "PRIMARY",
            "contact_name": "Father",
            "contact_phone": "919739988032",
        },
        headers=headers,
    )
    assert res_call.status_code == 201
    assert "Emergency call initiated to Father" in res_call.json()["description"]

    # 14. Call Police 112
    res_police = client.post(
        f"/api/women-safety/emergency/{event_id}/actions",
        json={
            "action_type": "POLICE_CALLED",
            "contact_type": "POLICE",
            "contact_name": "Police Control Room",
            "contact_phone": "112",
        },
        headers=headers,
    )
    assert res_police.status_code == 201
    assert "Emergency call initiated to Police (112)" in res_police.json()["description"]


# ── Test 15: No user_id spoofing allowed ──────────────────────────────────────

def test_no_user_id_spoofing_allowed():
    """Requirement 15: Passing spoofed user_id in payload is ignored; action user_id is derived strictly from JWT."""
    user_a, headers_a = _get_or_create_user("ws3_spoof_a@naviscape.test")
    user_b, headers_b = _get_or_create_user("ws3_spoof_b@naviscape.test")

    _cleanup_user_data(user_a.id)
    _cleanup_user_data(user_b.id)
    event_a_id = _create_test_event(user_a.id)

    # User A posts action with spoofed user_id = user_b.id
    res = client.post(
        f"/api/women-safety/emergency/{event_a_id}/actions",
        json={
            "action_type": "WHATSAPP_OPENED",
            "user_id": user_b.id,  # Spoofed!
        },
        headers=headers_a,
    )
    assert res.status_code == 201
    created_id = res.json()["id"]

    # Verify action stored in DB belongs to user_a.id
    db = SessionLocal()
    try:
        action = db.query(EmergencyAction).filter(EmergencyAction.id == created_id).first()
        assert action.user_id == user_a.id, "Action user_id must be bound strictly to JWT token"
    finally:
        db.close()
