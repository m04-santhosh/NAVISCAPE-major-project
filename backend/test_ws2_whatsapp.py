"""
NAVISCAPE Women Safety Test Suite — WS-2: WhatsApp Emergency Alert Flow
Deterministic unit and integration tests covering:

1. Phone normalization (9739988032 -> 919739988032).
2. Phone normalization (+91 9739988032 -> 919739988032).
3. Phone normalization (+919739988032 & 91 9739988032 -> 919739988032).
4. Invalid phone number rejected.
5. Emergency message contains actual latitude & longitude.
6. Emergency message contains Google Maps link.
7. Emergency message contains emergency alert wording.
8. Message URL encoding works.
9. wa.me URL generation works.
10. Trusted contacts are included in whatsapp-alerts.
11. Invalid/missing contact numbers handled gracefully.
12. User A cannot access User B's emergency alerts (tenant isolation).
"""

import pytest
from urllib.parse import unquote
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, init_db
from app.models.user import User
from app.models.emergency_profile import EmergencyProfile, TrustedContact
from app.models.emergency_event import EmergencyEvent
from app.middleware.auth import create_access_token, hash_pin
from app.services.whatsapp_service import (
    normalize_whatsapp_number,
    generate_emergency_message,
    generate_whatsapp_url,
)

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
        db.query(EmergencyEvent).filter(EmergencyEvent.user_id == user_id).delete()
        db.query(TrustedContact).filter(TrustedContact.user_id == user_id).delete()
        db.query(EmergencyProfile).filter(EmergencyProfile.user_id == user_id).delete()
        db.commit()
    finally:
        db.close()


# ── 1. Phone Normalization Tests ─────────────────────────────────────────────

def test_phone_normalization_standard_10_digits():
    """Requirement 1: 9739988032 -> 919739988032"""
    assert normalize_whatsapp_number("9739988032") == "919739988032"


def test_phone_normalization_with_plus_91_space():
    """Requirement 2: +91 9739988032 -> 919739988032"""
    assert normalize_whatsapp_number("+91 9739988032") == "919739988032"


def test_phone_normalization_variations():
    """Requirement 3: +919739988032 & 91 9739988032 -> 919739988032"""
    assert normalize_whatsapp_number("+919739988032") == "919739988032"
    assert normalize_whatsapp_number("91 9739988032") == "919739988032"
    assert normalize_whatsapp_number("09739988032") == "919739988032"


def test_invalid_phone_number_rejected():
    """Requirement 4: Invalid phone numbers raise ValueError."""
    with pytest.raises(ValueError):
        normalize_whatsapp_number("12345")

    with pytest.raises(ValueError):
        normalize_whatsapp_number("")

    with pytest.raises(ValueError):
        normalize_whatsapp_number("invalid_phone")


# ── 2. Emergency Message Generator Tests ─────────────────────────────────────

def test_emergency_message_contains_coordinates_maps_link_wording():
    """Requirements 5, 6, 7: Message contains latitude, longitude, Maps link, emergency wording."""
    lat = 12.9716
    lng = 77.5946
    msg = generate_emergency_message(
        user_name="Aarav",
        latitude=lat,
        longitude=lng,
        accuracy_m=8.0,
        triggered_at="05 Oct 2026, 9:30 PM",
    )

    # 5. Latitude & Longitude
    assert "12.9716" in msg
    assert "77.5946" in msg

    # 6. Google Maps Link
    assert "https://www.google.com/maps?q=12.9716,77.5946" in msg

    # 7. Emergency wording
    assert "🚨 NAVISCAPE EMERGENCY ALERT" in msg
    assert "An emergency SOS has been activated." in msg
    assert "Please contact me immediately." in msg


# ── 3. WhatsApp URL Generation & Encoding Tests ──────────────────────────────

def test_whatsapp_url_generation_and_encoding():
    """Requirements 8 & 9: wa.me URL generation and URL encoding work properly."""
    phone = "+91 9739988032"
    msg = "Emergency! Location: https://www.google.com/maps?q=12.9716,77.5946"
    url = generate_whatsapp_url(phone, msg)

    assert url.startswith("https://wa.me/919739988032?text=")
    encoded_part = url.split("?text=")[1]
    assert unquote(encoded_part) == msg


# ── 4. Endpoint & Contact Resolution Integration Tests ───────────────────────

def test_whatsapp_alerts_endpoint_includes_trusted_contacts():
    """Requirements 10 & 11: get_whatsapp_alerts includes trusted contacts with valid wa.me URLs."""
    user, headers = _get_or_create_user("ws2_contacts_user@naviscape.test")
    _cleanup_user_data(user.id)

    db = SessionLocal()
    try:
        profile = EmergencyProfile(
            user_id=user.id,
            emergency_mobile="9739988032",
            location_sharing_consent=True,
        )
        db.add(profile)

        c1 = TrustedContact(
            user_id=user.id,
            contact_name="Aarav Sharma",
            relationship="Brother",
            mobile_number="+91 9876543210",
            whatsapp_number="9876543210",
            whatsapp_alert_consent=True,
        )
        c2 = TrustedContact(
            user_id=user.id,
            contact_name="Priya Patel",
            relationship="Friend",
            mobile_number="91 9123456789",
            whatsapp_number="9123456789",
            whatsapp_alert_consent=True,
        )
        db.add_all([c1, c2])
        db.commit()

        event = EmergencyEvent(
            user_id=user.id,
            status="ACTIVE",
            latitude=12.9716,
            longitude=77.5946,
            location_accuracy_m=5.0,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        event_id = event.id
    finally:
        db.close()

    res = client.get(f"/api/women-safety/emergency-events/{event_id}/whatsapp-alerts", headers=headers)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    data = res.json()
    assert data["event_id"] == event_id
    assert data["latitude"] == pytest.approx(12.9716, abs=1e-5)
    assert data["longitude"] == pytest.approx(77.5946, abs=1e-5)

    alerts = data["alerts"]
    assert len(alerts) == 2, f"Expected 2 trusted contact alerts, got {len(alerts)}"

    tc1 = alerts[0]
    assert tc1["contact_name"] == "Aarav Sharma"
    assert tc1["whatsapp_available"] is True
    assert "https://wa.me/919876543210?text=" in tc1["whatsapp_url"]

    tc2 = alerts[1]
    assert tc2["contact_name"] == "Priya Patel"
    assert tc2["whatsapp_available"] is True
    assert "https://wa.me/919123456789?text=" in tc2["whatsapp_url"]


def test_invalid_trusted_contact_handled_gracefully():
    """Requirement 11: Invalid or missing phone number is handled gracefully without failing the request."""
    user, headers = _get_or_create_user("ws2_invalid_contact_user@naviscape.test")
    _cleanup_user_data(user.id)

    db = SessionLocal()
    try:
        c1 = TrustedContact(
            user_id=user.id,
            contact_name="Invalid Contact",
            relationship="Other",
            mobile_number="invalid_num",
            whatsapp_number=None,
            whatsapp_alert_consent=False,
        )
        db.add(c1)
        event = EmergencyEvent(user_id=user.id, status="ACTIVE", latitude=12.97, longitude=77.59)
        db.add(event)
        db.commit()
        event_id = event.id
    finally:
        db.close()

    res = client.get(f"/api/women-safety/emergency-events/{event_id}/whatsapp-alerts", headers=headers)
    assert res.status_code == 200
    alerts = res.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["whatsapp_available"] is False
    assert alerts[0]["whatsapp_url"] is None


def test_user_isolation_for_whatsapp_alerts():
    """Requirement 12: User A cannot fetch WhatsApp alerts for User B's emergency event."""
    user_a, headers_a = _get_or_create_user("ws2_iso_a@naviscape.test")
    user_b, headers_b = _get_or_create_user("ws2_iso_b@naviscape.test")

    _cleanup_user_data(user_a.id)
    _cleanup_user_data(user_b.id)

    db = SessionLocal()
    try:
        event_a = EmergencyEvent(user_id=user_a.id, status="ACTIVE", latitude=12.97, longitude=77.59)
        db.add(event_a)
        db.commit()
        event_a_id = event_a.id
    finally:
        db.close()

    res = client.get(f"/api/women-safety/emergency-events/{event_a_id}/whatsapp-alerts", headers=headers_b)
    assert res.status_code == 404, "Must return 404 when querying another user's emergency event"
