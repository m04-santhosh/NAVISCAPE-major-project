"""
Tests for NAVISCAPE Email Service & Authentication OTP / Password Reset Flow
Uses unittest/pytest with mocked SMTP connections to ensure security and determinism.
"""

import os
import sys
import smtplib
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app
from app.config import settings
from app.email_service import EmailService, OTPStore, email_service, otp_store
from app.database import get_db, Base, engine
from app.models.user import User
from app.middleware.auth import hash_password, create_access_token

client = TestClient(app)


# ── OTPStore Unit Tests ──────────────────────────────────────────────────────

def test_otp_store_generation_and_verification():
    store = OTPStore(default_ttl_seconds=60, max_attempts=3)
    email = "test.user@example.com"
    
    # 1. Generate OTP
    otp = store.generate_otp(email, purpose="password_reset")
    assert len(otp) == 6
    assert otp.isdigit()

    # 2. Verify without consuming
    valid, msg = store.verify_otp(email, otp, purpose="password_reset", consume=False)
    assert valid is True
    assert "successfully" in msg

    # 3. Verify and consume
    valid, msg = store.verify_otp(email, otp, purpose="password_reset", consume=True)
    assert valid is True

    # 4. Once consumed, should fail
    valid, msg = store.verify_otp(email, otp, purpose="password_reset")
    assert valid is False


def test_otp_store_expiry():
    store = OTPStore(default_ttl_seconds=1, max_attempts=3)
    email = "expired.user@example.com"
    otp = store.generate_otp(email, purpose="password_reset")
    
    # Wait for TTL to elapse
    time.sleep(1.1)
    
    valid, msg = store.verify_otp(email, otp, purpose="password_reset")
    assert valid is False
    assert "expired" in msg.lower()


def test_otp_store_rate_limiting():
    store = OTPStore(default_ttl_seconds=60, max_attempts=3)
    email = "brute.force@example.com"
    otp = store.generate_otp(email, purpose="password_reset")

    # 3 wrong attempts
    for _ in range(3):
        valid, msg = store.verify_otp(email, "000000", purpose="password_reset")
        assert valid is False

    # 4th attempt should lock out
    valid, msg = store.verify_otp(email, otp, purpose="password_reset")
    assert valid is False
    assert "too many failed attempts" in msg.lower()


# ── EmailService Mocked SMTP Tests ───────────────────────────────────────────

def test_email_service_send_email_mocked_success():
    service = EmailService()
    
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        # Override credentials on settings temporarily
        with patch.object(settings, "SMTP_HOST", "smtp.gmail.com"), \
             patch.object(settings, "SMTP_USERNAME", "mock@gmail.com"), \
             patch.object(settings, "SMTP_PASSWORD", "mock-app-password"):
            
            result = service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                body_text="Test Message",
                body_html="<p>Test Message</p>",
            )

            assert result["success"] is True
            assert result["recipient"] == "recipient@example.com"
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("mock@gmail.com", "mock-app-password")
            mock_server.send_message.assert_called_once()


def test_email_service_send_email_auth_failure_handling():
    service = EmailService()
    
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        with patch.object(settings, "SMTP_HOST", "smtp.gmail.com"), \
             patch.object(settings, "SMTP_USERNAME", "mock@gmail.com"), \
             patch.object(settings, "SMTP_PASSWORD", "super-secret-password-123"):
            
            result = service.send_email(
                to_email="recipient@example.com",
                subject="Test",
                body_text="Test",
            )

            assert result["success"] is False
            assert "authentication failed" in result["message"].lower()
            # Ensure the password is NEVER in result message
            assert "super-secret-password-123" not in str(result)


def test_email_service_invalid_recipient():
    service = EmailService()
    result = service.send_email(
        to_email="invalid-email-no-at",
        subject="Test",
        body_text="Test",
    )
    assert result["success"] is False
    assert "invalid recipient" in result["message"].lower()


def test_email_service_unconfigured():
    service = EmailService()
    with patch.object(settings, "SMTP_PASSWORD", ""):
        result = service.send_email(
            to_email="user@example.com",
            subject="Test",
            body_text="Test",
        )
        assert result["success"] is False
        assert "not configured" in result["message"].lower()


# ── Integration / API Endpoint Tests ──────────────────────────────────────────

def test_api_forgot_password_and_reset_flow():
    # Setup a test user in DB
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        test_email = "smtp_test_user@naviscape.com"
        db.query(User).filter(User.email == test_email).delete()
        db.commit()

        user = User(
            email=test_email,
            full_name="SMTP Test User",
            username=test_email,
            hashed_password=hash_password("OldPassword123"),
            pin_hash=hash_password("OldPassword123"),
            email_verified=True,
            is_active=True,
        )
        db.add(user)
        db.commit()

        # 1. Request forgot password
        with patch.object(settings, "SMTP_PASSWORD", ""):
            response = client.post("/api/auth/forgot-password", json={"email": test_email})
            assert response.status_code == 200
            assert "verification code" in response.json()["message"].lower()

        # Retrieve generated OTP from store
        otp_key = f"{test_email}::password_reset"
        otp = otp_store._store[otp_key]["otp"]

        # 2. Verify OTP endpoint
        verify_res = client.post("/api/auth/verify-otp", json={"email": test_email, "otp": otp})
        assert verify_res.status_code == 200
        assert "verified successfully" in verify_res.json()["message"].lower()

        # 3. Reset password with wrong OTP
        wrong_res = client.post(
            "/api/auth/reset-password",
            json={
                "email": test_email,
                "otp": "999999",
                "new_password": "NewSecretPassword123",
                "confirm_new_password": "NewSecretPassword123",
            },
        )
        assert wrong_res.status_code == 400

        # 4. Reset password with correct OTP
        reset_res = client.post(
            "/api/auth/reset-password",
            json={
                "email": test_email,
                "otp": otp,
                "new_password": "NewSecretPassword123",
                "confirm_new_password": "NewSecretPassword123",
            },
        )
        assert reset_res.status_code == 200
        assert "reset successfully" in reset_res.json()["message"].lower()

        # 5. Login with new password
        login_res = client.post(
            "/api/auth/login",
            json={"email": test_email, "password": "NewSecretPassword123"},
        )
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()

    finally:
        db.query(User).filter(User.email == test_email).delete()
        db.commit()
        db.close()


def test_api_dev_test_email_endpoint():
    with patch.object(email_service, "send_email") as mock_send:
        mock_send.return_value = {"success": True, "message": "Email sent successfully."}

        res = client.post(
            "/api/test-email",
            json={"recipient_email": "tester@example.com"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "success"
        mock_send.assert_called_once()


# ── Registration Email OTP Flow Tests ────────────────────────────────────────

def test_registration_otp_full_flow():
    from app.database import SessionLocal
    db = SessionLocal()
    test_email = "new_registered_user@naviscape.com"
    test_password = "SecurePassword123!"
    test_name = "New Verified User"

    try:
        # Clean up any leftover test data
        db.query(User).filter(User.email == test_email).delete()
        db.commit()
        otp_store.clear(test_email, purpose="registration")

        # 1. Step 1: Registration Request
        with patch.object(email_service, "send_otp_email") as mock_send_otp:
            mock_send_otp.return_value = {"success": True}

            reg_res = client.post(
                "/api/auth/register",
                json={
                    "full_name": test_name,
                    "email": test_email,
                    "password": test_password,
                    "confirm_password": test_password,
                },
            )
            assert reg_res.status_code == 200
            data = reg_res.json()
            assert data["status"] == "otp_required"
            assert data["email"] == test_email
            assert "otp" not in data  # Never expose OTP in response
            assert test_password not in str(data)  # Never expose password

            # 2. Check that user is NOT created in DB yet
            pending_user = db.query(User).filter(User.email == test_email).first()
            assert pending_user is None

        # 3. Retrieve OTP from OTPStore (purpose: registration)
        otp_key = f"{test_email}::registration"
        assert otp_key in otp_store._store
        correct_otp = otp_store._store[otp_key]["otp"]
        assert len(correct_otp) == 6
        assert correct_otp.isdigit()

        # 4. Wrong OTP is rejected
        wrong_otp_res = client.post(
            "/api/auth/register/verify-otp",
            json={
                "full_name": test_name,
                "email": test_email,
                "password": test_password,
                "confirm_password": test_password,
                "otp": "000000",
            },
        )
        assert wrong_otp_res.status_code == 400
        assert "invalid otp" in wrong_otp_res.json()["detail"].lower()

        # Ensure user is STILL not in DB
        assert db.query(User).filter(User.email == test_email).first() is None

        # 5. Correct OTP creates the account
        with patch.object(email_service, "send_welcome_email") as mock_welcome:
            mock_welcome.return_value = {"success": True}

            verify_res = client.post(
                "/api/auth/register/verify-otp",
                json={
                    "full_name": test_name,
                    "email": test_email,
                    "password": test_password,
                    "confirm_password": test_password,
                    "otp": correct_otp,
                },
            )
            assert verify_res.status_code == 201
            verify_data = verify_res.json()
            assert "access_token" in verify_data
            assert verify_data["user"]["email"] == test_email
            assert verify_data["user"]["full_name"] == test_name
            assert verify_data["user"]["email_verified"] is True

        # 6. Verify password in DB is hashed and NOT plain text
        created_user = db.query(User).filter(User.email == test_email).first()
        assert created_user is not None
        assert created_user.hashed_password != test_password
        assert created_user.hashed_password.startswith("$2b$") or created_user.hashed_password.startswith("$2a$")
        assert created_user.email_verified is True

        # 7. Verify login works with newly registered credentials
        login_res = client.post(
            "/api/auth/login",
            json={"email": test_email, "password": test_password},
        )
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()

        # 8. Attempting to register again with same email fails
        duplicate_res = client.post(
            "/api/auth/register",
            json={
                "full_name": test_name,
                "email": test_email,
                "password": test_password,
                "confirm_password": test_password,
            },
        )
        assert duplicate_res.status_code == 400
        assert "already exists" in duplicate_res.json()["detail"].lower()

    finally:
        db.query(User).filter(User.email == test_email).delete()
        db.commit()
        db.close()


def test_registration_otp_resend_and_expiry():
    from app.database import SessionLocal
    db = SessionLocal()
    test_email = "resend_test_user@naviscape.com"
    test_password = "SecurePassword456!"
    test_name = "Resend Test User"

    try:
        db.query(User).filter(User.email == test_email).delete()
        db.commit()
        otp_store.clear(test_email, purpose="registration")

        # 1. Initial request
        res1 = client.post(
            "/api/auth/register",
            json={
                "full_name": test_name,
                "email": test_email,
                "password": test_password,
                "confirm_password": test_password,
            },
        )
        assert res1.status_code == 200
        otp1 = otp_store._store[f"{test_email}::registration"]["otp"]

        # 2. Resend OTP
        resend_res = client.post(
            "/api/auth/register/resend-otp",
            json={"email": test_email, "full_name": test_name},
        )
        assert resend_res.status_code == 200
        assert "verification code has been sent" in resend_res.json()["message"].lower()

        otp2 = otp_store._store[f"{test_email}::registration"]["otp"]
        assert len(otp2) == 6

        # 3. Simulate OTP expiration
        otp_store._store[f"{test_email}::registration"]["expiry"] = time.time() - 10

        exp_res = client.post(
            "/api/auth/register/verify-otp",
            json={
                "full_name": test_name,
                "email": test_email,
                "password": test_password,
                "confirm_password": test_password,
                "otp": otp2,
            },
        )
        assert exp_res.status_code == 400
        assert "expired" in exp_res.json()["detail"].lower()

    finally:
        db.query(User).filter(User.email == test_email).delete()
        db.commit()
        db.close()


def test_registration_otp_rate_limiting_lockout():
    from app.database import SessionLocal
    db = SessionLocal()
    test_email = "lockout_test_user@naviscape.com"
    test_password = "SecurePassword789!"
    test_name = "Lockout Test User"

    try:
        db.query(User).filter(User.email == test_email).delete()
        db.commit()
        otp_store.clear(test_email, purpose="registration")

        # Request OTP
        client.post(
            "/api/auth/register",
            json={
                "full_name": test_name,
                "email": test_email,
                "password": test_password,
                "confirm_password": test_password,
            },
        )
        correct_otp = otp_store._store[f"{test_email}::registration"]["otp"]

        # Enter wrong OTP 5 times (max_attempts = 5)
        for _ in range(5):
            r = client.post(
                "/api/auth/register/verify-otp",
                json={
                    "full_name": test_name,
                    "email": test_email,
                    "password": test_password,
                    "confirm_password": test_password,
                    "otp": "999999",
                },
            )
            assert r.status_code == 400

        # 6th attempt with correct OTP should be locked out
        lockout_res = client.post(
            "/api/auth/register/verify-otp",
            json={
                "full_name": test_name,
                "email": test_email,
                "password": test_password,
                "confirm_password": test_password,
                "otp": correct_otp,
            },
        )
        assert lockout_res.status_code == 400
        assert "too many failed attempts" in lockout_res.json()["detail"].lower()

    finally:
        db.query(User).filter(User.email == test_email).delete()
        db.commit()
        db.close()

