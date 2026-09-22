"""
NAVISCAPE Email Service
Centralized Gmail SMTP integration for sending transactional emails and OTP verification.
Uses Python's standard smtplib and email.message modules with STARTTLS on port 587.
Credentials and configuration are loaded securely from application settings.
"""

import os
import smtplib
import ssl
import logging
from email.message import EmailMessage
from typing import Optional, Dict, Any

from ..config import settings

logger = logging.getLogger("naviscape.email_service")


class EmailService:
    """
    Centralized Gmail SMTP client for NAVISCAPE.
    Connects to SMTP host using STARTTLS on port 587.
    """

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
        return settings.SMTP_FROM_EMAIL or self.username or "noreply@naviscape.com"

    @property
    def from_name(self) -> str:
        return settings.SMTP_FROM_NAME or "NAVISCAPE"

    @property
    def is_configured(self) -> bool:
        """Return True if SMTP credentials are provided with a valid email username."""
        user = (self.username or "").strip()
        pwd = (self.password or "").strip()
        return bool(
            user
            and pwd
            and "@" in user
            and "replace" not in user.lower()
            and "placeholder" not in user.lower()
            and user.lower() != "naviscape"
        )

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an email via Gmail SMTP using STARTTLS.
        Completes synchronous delivery before returning result.
        """
        if not self.is_configured:
            logger.warning(
                "[EMAIL] SMTP is not configured. Email to %s with subject '%s' skipped in development/test.",
                to_email,
                subject,
            )
            return {
                "success": True,
                "message": "SMTP not configured; simulated email delivery in development mode.",
                "simulated": True,
            }

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email
        msg.set_content(body_text)

        if body_html:
            msg.add_alternative(body_html, subtype="html")

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info("[EMAIL] Email sent successfully to %s: '%s'", to_email, subject)
            return {
                "success": True,
                "message": f"Email delivered successfully to {to_email}.",
                "simulated": False,
            }
        except smtplib.SMTPAuthenticationError as auth_err:
            logger.error("[EMAIL] SMTP Authentication failed for %s: %s", self.username, auth_err)
            return {
                "success": False,
                "message": f"SMTP Authentication failed: {str(auth_err)}",
            }
        except Exception as err:
            logger.error("[EMAIL] Failed to send email to %s: %s", to_email, err)
            return {
                "success": False,
                "message": f"Failed to send email: {str(err)}",
            }

    def send_otp_email(
        self,
        to_email: str,
        otp_code: str,
        user_name: Optional[str] = None,
        purpose: str = "Account Registration",
        validity_minutes: int = 10,
    ) -> Dict[str, Any]:
        """
        Send a branded OTP verification email.
        """
        display_name = (user_name or "Explorer").strip()
        subject = f"{otp_code} is your {self.from_name} verification code"

        plain_text = (
            f"Hello {display_name},\n\n"
            f"Your verification code for {purpose} is: {otp_code}\n\n"
            f"This code will expire in {validity_minutes} minutes.\n"
            f"If you did not request this code, please ignore this email.\n\n"
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


# Global singleton instance
email_service = EmailService()


def send_otp_email(
    to_email: str,
    otp: str,
    user_name: Optional[str] = None,
    purpose: str = "Account Registration",
    validity_minutes: int = 10,
) -> Dict[str, Any]:
    """
    Convenience function to send an OTP email synchronously.
    """
    return email_service.send_otp_email(
        to_email=to_email,
        otp_code=otp,
        user_name=user_name,
        purpose=purpose,
        validity_minutes=validity_minutes,
    )
