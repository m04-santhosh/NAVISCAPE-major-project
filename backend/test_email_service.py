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
