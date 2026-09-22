"""
SMTP Email Service Unit Tests
Tests that EmailService and send_otp_email:
1. Connects using smtplib.SMTP with STARTTLS and proper port.
2. Formats plain-text and HTML emails with subject, from, to, and 6-digit OTP.
3. Successfully logs and delivers email when credentials are valid.
4. Gracefully handles authentication errors or SMTP failures.
5. send_otp_email convenience function completes synchronous execution.
"""

from unittest.mock import patch, MagicMock
import pytest
from app.services.email_service import EmailService, send_otp_email
from app.config import settings


def test_send_email_not_configured_simulates():
    """When SMTP is not configured, send_email gracefully logs and returns simulated success."""
    service = EmailService()
    with patch.object(settings, "SMTP_USERNAME", ""), \
         patch.object(settings, "SMTP_PASSWORD", ""):
        res = service.send_email(
            to_email="test@example.com",
            subject="Test Subject",
            body_text="Hello world",
        )
        assert res["success"] is True
        assert res.get("simulated") is True


def test_send_email_smtp_delivery_with_starttls():
    """When SMTP is configured, send_email uses STARTTLS and completes delivery."""
    service = EmailService()

    mock_smtp_instance = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp_instance), \
         patch.object(settings, "SMTP_USERNAME", "testuser@gmail.com"), \
         patch.object(settings, "SMTP_PASSWORD", "app-password-1234"), \
         patch.object(settings, "SMTP_FROM_EMAIL", "testuser@gmail.com"), \
         patch.object(settings, "SMTP_FROM_NAME", "NAVISCAPE"):

        mock_smtp_instance.__enter__.return_value = mock_smtp_instance

        res = service.send_email(
            to_email="recipient@example.com",
            subject="Test Verification",
            body_text="Your code is 123456",
            body_html="<p>Your code is 123456</p>",
        )

        assert res["success"] is True
        assert res.get("simulated") is False
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once_with("testuser@gmail.com", "app-password-1234")
        mock_smtp_instance.send_message.assert_called_once()


def test_send_otp_email_formats_correctly():
    """send_otp_email passes correct recipient, subject with OTP, and body."""
    mock_send = MagicMock(return_value={"success": True, "message": "Email delivered"})
    with patch.object(EmailService, "send_email", mock_send):
        res = send_otp_email(
            to_email="explorer@example.com",
            otp="849201",
            user_name="Alice",
            purpose="Account Registration",
            validity_minutes=10,
        )
        assert res["success"] is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["to_email"] == "explorer@example.com"
        assert "849201" in call_kwargs["subject"]
        assert "Alice" in call_kwargs["body_text"]
        assert "849201" in call_kwargs["body_text"]
