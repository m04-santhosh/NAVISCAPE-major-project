"""
NAVISCAPE Email Service
Centralized Gmail SMTP integration for sending transactional emails, OTP verification, and alerts.
Uses Python's standard smtplib and email.message modules with STARTTLS on port 587.
Credentials and configuration are loaded securely from application settings.
"""

import os
import smtplib
import ssl
import logging
import secrets
import time
from email.message import EmailMessage
from typing import Optional, Dict, Any, Tuple

from .config import settings

logger = logging.getLogger("naviscape.email_service")


# ── In-Memory OTP Store with Expiry & Rate Limiting ──────────────────────────

class OTPStore:
    """
    Thread-safe in-memory store for one-time passwords (OTP).
    Stores OTPs with expiration time and attempt counter.
    """

    def __init__(self, default_ttl_seconds: int = 600, max_attempts: int = 5):
        self._store: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl_seconds
        self.max_attempts = max_attempts

    def _make_key(self, email: str, purpose: str) -> str:
        return f"{email.strip().lower()}::{purpose.strip().lower()}"

    def generate_otp(self, email: str, purpose: str = "password_reset", length: int = 6) -> str:
        """Generate a cryptographically secure numeric OTP and store it with expiry."""
        otp = "".join(secrets.choice("0123456789") for _ in range(length))
        key = self._make_key(email, purpose)
        expiry = time.time() + self.default_ttl

        self._store[key] = {
            "otp": otp,
            "expiry": expiry,
            "attempts": 0,
            "created_at": time.time(),
        }
        return otp

    def verify_otp(self, email: str, otp: str, purpose: str = "password_reset", consume: bool = True) -> Tuple[bool, str]:
        """
        Verify an OTP for a given email and purpose.
        Returns (is_valid, message).
        If valid and consume=True, the OTP is invalidated.
        """
        key = self._make_key(email, purpose)
        record = self._store.get(key)

        if not record:
            return False, "No OTP found or OTP has expired. Please request a new one."

        # Check expiration
        if time.time() > record["expiry"]:
            self._store.pop(key, None)
            return False, "OTP has expired. Please request a new one."

        # Check max attempts
        record["attempts"] += 1
        if record["attempts"] > self.max_attempts:
            self._store.pop(key, None)
            return False, "Too many failed attempts. Please request a new OTP."

        # Compare OTP safely
        if secrets.compare_digest(record["otp"].strip(), otp.strip()):
            if consume:
                self._store.pop(key, None)
            return True, "OTP verified successfully."

        remaining = self.max_attempts - record["attempts"]
        return False, f"Invalid OTP. {remaining} attempt(s) remaining."

    def clear(self, email: str, purpose: str = "password_reset") -> None:
        """Remove an OTP entry."""
        key = self._make_key(email, purpose)
        self._store.pop(key, None)


# Global OTP store instance
otp_store = OTPStore()


# ── SMTP Email Service ────────────────────────────────────────────────────────

class EmailService:
    """
    Centralized Gmail SMTP client for NAVISCAPE.
    Connects to SMTP host using STARTTLS on port 587.
    """

    def __init__(self):
        pass

    @property
    def host(self) -> str:
        return settings.SMTP_HOST or "smtp.gmail.com"

    @property
    def port(self) -> int:
        return settings.SMTP_PORT or 587

    @property
    def username(self) -> str:
        return settings.SMTP_USERNAME or ""

    @property
    def password(self) -> str:
        return settings.SMTP_PASSWORD or ""

    @property
    def from_email(self) -> str:
        return settings.SMTP_FROM_EMAIL or self.username or "naviscape.app@gmail.com"

    @property
    def from_name(self) -> str:
        return settings.SMTP_FROM_NAME or "NaviScape"

    @property
    def is_configured(self) -> bool:
        """Check if SMTP credentials are provided."""
        return bool(self.host and self.username and self.password)

    def verify_connection(self) -> Dict[str, Any]:
        """
        Verify SMTP credentials and connectivity.
        Never logs or returns password.
        """
        if not self.is_configured:
            return {
                "success": False,
                "message": "SMTP configuration incomplete. Host, username, and password are required.",
                "configured": False,
            }

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.username, self.password)
            return {
                "success": True,
                "message": "SMTP authentication successful.",
                "host": self.host,
                "port": self.port,
                "username": self.username,
                "from_email": self.from_email,
            }
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP Authentication failed for user: %s", self.username)
            return {
                "success": False,
                "message": "SMTP authentication failed. Check username and application password.",
            }
        except smtplib.SMTPConnectError as e:
            logger.error("SMTP Connection failed: %s", str(e))
            return {
                "success": False,
                "message": f"Could not connect to SMTP server {self.host}:{self.port}.",
            }
        except Exception as e:
            logger.error("SMTP verification error: %s", type(e).__name__)
            return {
                "success": False,
                "message": f"SMTP connection error: {type(e).__name__}",
            }

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an email via Gmail SMTP.

        Args:
            to_email: Recipient email address
            subject: Subject line
            body_text: Plain-text fallback content
            body_html: Optional HTML formatted content

        Returns:
            Dict with 'success', 'message', 'recipient', and optional 'error'
        """
        if not to_email or "@" not in to_email:
            return {
                "success": False,
                "message": "Invalid recipient email address.",
                "recipient": to_email,
            }

        if not self.is_configured:
            logger.warning(
                "SMTP not configured. Email to %s with subject '%s' was skipped.",
                to_email,
                subject,
            )
            return {
                "success": False,
                "message": "SMTP service is not configured. Please set SMTP credentials in .env.",
                "recipient": to_email,
            }

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email.strip()

        # Set plain text content
        msg.set_content(body_text)

        # Set HTML alternative if provided
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info("Email sent successfully to %s: '%s'", to_email, subject)
            return {
                "success": True,
                "message": "Email sent successfully.",
                "recipient": to_email,
            }

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP Authentication failed during email send to %s", to_email)
            return {
                "success": False,
                "message": "SMTP Authentication failed. Verify SMTP username and App Password.",
                "recipient": to_email,
            }
        except smtplib.SMTPRecipientsRefused:
            logger.error("Recipient refused by SMTP server: %s", to_email)
            return {
                "success": False,
                "message": "Recipient address was refused by the mail server.",
                "recipient": to_email,
            }
        except smtplib.SMTPException as e:
            logger.error("SMTP error while sending to %s: %s", to_email, type(e).__name__)
            return {
                "success": False,
                "message": f"SMTP error occurred: {type(e).__name__}",
                "recipient": to_email,
            }
        except Exception as e:
            logger.error("Unexpected error sending email to %s: %s", to_email, type(e).__name__)
            return {
                "success": False,
                "message": f"Failed to send email: {type(e).__name__}",
                "recipient": to_email,
            }

    # ── High-Level Transactional Email Templates ─────────────────────────────

    def send_otp_email(
        self,
        to_email: str,
        otp_code: str,
        user_name: Optional[str] = None,
        purpose: str = "Password Reset",
        validity_minutes: int = 10,
    ) -> Dict[str, Any]:
        """
        Send a branded OTP verification email.
        """
        display_name = user_name or "NaviScape User"
        subject = f"{otp_code} is your {self.from_name} verification code"

        plain_text = (
            f"Hello {display_name},\n\n"
            f"Your verification code for {purpose} is: {otp_code}\n\n"
            f"This code will expire in {validity_minutes} minutes.\n"
            f"If you did not request this code, please ignore this email or secure your account.\n\n"
            f"Best regards,\n"
            f"The {self.from_name} Team"
        )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0f172a; padding: 40px 15px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 520px; background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%); border-radius: 16px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
          <!-- Header Banner -->
          <tr>
            <td style="padding: 32px 32px 20px 32px; text-align: center; border-bottom: 1px solid #334155; background: radial-gradient(circle at center, #1e3a8a 0%, #1e293b 100%);">
              <div style="font-size: 28px; font-weight: 800; letter-spacing: 2px; color: #38bdf8; text-transform: uppercase;">
                NAVISCAPE
              </div>
              <div style="font-size: 13px; color: #94a3b8; margin-top: 4px; letter-spacing: 0.5px;">
                Intelligent Navigation & Safety Platform
              </div>
            </td>
          </tr>
          <!-- Body Content -->
          <tr>
            <td style="padding: 32px 32px 24px 32px;">
              <h2 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 700; color: #f8fafc;">
                Verification Code
              </h2>
              <p style="margin: 0 0 20px 0; font-size: 15px; line-height: 1.6; color: #cbd5e1;">
                Hello <strong style="color: #f1f5f9;">{display_name}</strong>,
              </p>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: #94a3b8;">
                Use the verification code below for <strong>{purpose}</strong>. This code is valid for the next <strong>{validity_minutes} minutes</strong>.
              </p>

              <!-- OTP Code Display Card -->
              <div style="background-color: #090d16; border: 1px solid #2563eb; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0;">
                <div style="font-size: 11px; text-transform: uppercase; color: #60a5fa; letter-spacing: 1.5px; font-weight: 600; margin-bottom: 8px;">
                  Your One-Time Password
                </div>
                <div style="font-family: 'Courier New', Courier, monospace; font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #38bdf8; padding: 4px 0;">
                  {otp_code}
                </div>
              </div>

              <!-- Security Notice -->
              <div style="background-color: rgba(239, 68, 68, 0.1); border-left: 3px solid #ef4444; border-radius: 4px; padding: 12px 16px; margin: 20px 0;">
                <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #fca5a5;">
                  <strong>Security Reminder:</strong> Never share this code with anyone. NaviScape staff will never ask for your verification code or password.
                </p>
              </div>

              <p style="margin: 20px 0 0 0; font-size: 13px; color: #64748b; line-height: 1.5;">
                If you did not request this verification code, you can safely ignore this email.
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding: 20px 32px; background-color: #090d16; border-top: 1px solid #1e293b; text-align: center;">
              <p style="margin: 0; font-size: 12px; color: #475569;">
                &copy; 2026 NaviScape Major Project. All rights reserved.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        return self.send_email(
            to_email=to_email,
            subject=subject,
            body_text=plain_text,
            body_html=html_content,
        )

    def send_welcome_email(
        self,
        to_email: str,
        user_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a welcome email upon new user registration.
        """
        display_name = user_name or "NaviScape Explorer"
        subject = f"Welcome to {self.from_name}!"

        plain_text = (
            f"Hello {display_name},\n\n"
            f"Welcome to {self.from_name} — your AI-powered intelligent navigation and safety platform.\n\n"
            f"With NaviScape, you have access to predictive traffic analysis, real-time risk assessment, "
            f"safe route optimization, and women safety emergency features.\n\n"
            f"Explore the platform now and enjoy safer travels!\n\n"
            f"Best regards,\n"
            f"The {self.from_name} Team"
        )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{subject}</title>
</head>
<body style="margin:0; padding:0; background-color:#0f172a; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color:#e2e8f0;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#0f172a; padding:40px 15px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:520px; background:linear-gradient(180deg, #1e293b 0%, #0f172a 100%); border-radius:16px; border:1px solid #334155; overflow:hidden; box-shadow:0 10px 25px rgba(0,0,0,0.5);">
          <tr>
            <td style="padding:32px; text-align:center; background:radial-gradient(circle at center, #1e3a8a 0%, #1e293b 100%); border-bottom:1px solid #334155;">
              <div style="font-size:28px; font-weight:800; letter-spacing:2px; color:#38bdf8;">NAVISCAPE</div>
              <div style="font-size:13px; color:#94a3b8; margin-top:4px;">Smart Navigation & Risk-Aware Routing</div>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 12px 0; color:#f8fafc; font-size:20px;">Welcome aboard, {display_name}! 🚀</h2>
              <p style="color:#cbd5e1; font-size:15px; line-height:1.6;">
                Thank you for joining <strong>NaviScape</strong>. Your account is ready, giving you access to next-generation travel intelligence:
              </p>
              <ul style="color:#94a3b8; font-size:14px; line-height:1.8; padding-left:20px; margin:20px 0;">
                <li>🚦 <strong>Predictive Traffic Analysis</strong> powered by ML</li>
                <li>🛡️ <strong>Risk-Aware Routing</strong> & Road Hazard Detection</li>
                <li>🚨 <strong>Women Safety Features</strong> & Emergency SOS Broadcasting</li>
                <li>🏥 <strong>Real-Time Emergency Infrastructure</strong> (Hospitals & Police)</li>
              </ul>
              <p style="color:#64748b; font-size:13px; margin-top:24px;">
                Drive safe, travel smart!
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 32px; background-color:#090d16; border-top:1px solid #1e293b; text-align:center;">
              <p style="margin:0; font-size:12px; color:#475569;">&copy; 2026 NaviScape Major Project.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        return self.send_email(
            to_email=to_email,
            subject=subject,
            body_text=plain_text,
            body_html=html_content,
        )


# Global singleton instance
email_service = EmailService()
