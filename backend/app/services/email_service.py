"""
Email Service — Gmail SMTP
Sends OTP emails for NAVISCAPE authentication flows.

Configuration (from backend/.env):
    SMTP_HOST       = smtp.gmail.com
    SMTP_PORT       = 587
    SMTP_USERNAME   = your-gmail@gmail.com
    SMTP_PASSWORD   = your-gmail-app-password  (NOT your Google account password)
    SMTP_FROM_EMAIL = your-gmail@gmail.com
    SMTP_FROM_NAME  = NAVISCAPE

SECURITY NOTES:
- OTP values are NEVER logged here.
- Credentials come exclusively from environment variables.
- SMTP_PASSWORD is a Gmail App Password — see https://myaccount.google.com/apppasswords
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import settings
from ..models.otp import OTPPurpose


class EmailDeliveryError(Exception):
    """Raised when email delivery fails."""
    pass


def _build_otp_html(otp: str, purpose: OTPPurpose, expire_minutes: int) -> str:
    """Build a professional HTML email body for the OTP."""
    if purpose == OTPPurpose.SIGNUP:
        heading = "Verify your email address"
        sub = "Enter the code below to complete your NAVISCAPE sign-up."
    else:
        heading = "Reset your PIN"
        sub = "Enter the code below to reset your NAVISCAPE PIN."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>NAVISCAPE Verification Code</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="520" cellpadding="0" cellspacing="0"
               style="background:#1e293b;border-radius:16px;border:1px solid #334155;overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#0891b2,#06b6d4);padding:32px 40px;text-align:center;">
              <h1 style="margin:0;font-size:28px;font-weight:800;color:#ffffff;letter-spacing:2px;
                          text-transform:uppercase;">NAVISCAPE</h1>
              <p style="margin:4px 0 0;font-size:13px;color:#cffafe;letter-spacing:1px;">
                Intelligent Navigation System
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px;">
              <h2 style="margin:0 0 8px;font-size:20px;font-weight:700;color:#e2e8f0;">{heading}</h2>
              <p style="margin:0 0 32px;font-size:15px;color:#94a3b8;line-height:1.6;">{sub}</p>

              <!-- OTP box -->
              <div style="background:#0f172a;border:2px solid #06b6d4;border-radius:12px;
                          padding:28px;text-align:center;margin:0 0 32px;">
                <p style="margin:0 0 8px;font-size:12px;font-weight:600;
                           color:#64748b;letter-spacing:2px;text-transform:uppercase;">
                  Verification Code
                </p>
                <p style="margin:0;font-size:44px;font-weight:800;
                           color:#06b6d4;letter-spacing:12px;font-family:monospace;">
                  {otp}
                </p>
              </div>

              <p style="margin:0 0 8px;font-size:14px;color:#64748b;text-align:center;">
                ⏱ This code expires in <strong style="color:#e2e8f0;">{expire_minutes} minutes</strong>.
              </p>
              <p style="margin:0;font-size:13px;color:#475569;text-align:center;">
                If you did not request this code, you can safely ignore this email.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#0f172a;border-top:1px solid #1e293b;
                        padding:20px 40px;text-align:center;">
              <p style="margin:0;font-size:12px;color:#334155;">
                © 2025 NAVISCAPE &nbsp;·&nbsp; Do not reply to this email.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_otp_text(otp: str, purpose: OTPPurpose, expire_minutes: int) -> str:
    """Plain-text fallback for email clients that don't support HTML."""
    action = "sign-up" if purpose == OTPPurpose.SIGNUP else "PIN reset"
    return (
        f"NAVISCAPE — Verification Code\n\n"
        f"Your NAVISCAPE {action} verification code is:\n\n"
        f"  {otp}\n\n"
        f"This code expires in {expire_minutes} minutes.\n\n"
        f"If you did not request this code, you can ignore this email.\n\n"
        f"— NAVISCAPE"
    )


def send_otp_email(to_email: str, otp: str, purpose: OTPPurpose) -> None:
    """
    Send an OTP verification email via Gmail SMTP.

    Args:
        to_email:  Recipient email address.
        otp:       The plaintext OTP (sent once here, never logged).
        purpose:   OTPPurpose.SIGNUP or OTPPurpose.FORGOT_PIN

    Raises:
        EmailDeliveryError: if SMTP is not configured or delivery fails.
    """
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        # SMTP not configured — warn clearly in server logs (no credentials exposed)
        raise EmailDeliveryError(
            "Email delivery is not configured. "
            "Set SMTP_USERNAME and SMTP_PASSWORD in backend/.env to enable OTP emails."
        )

    subject = "NAVISCAPE Verification Code"
    expire_minutes = settings.OTP_EXPIRE_MINUTES

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    msg.attach(MIMEText(_build_otp_text(otp, purpose, expire_minutes), "plain"))
    msg.attach(MIMEText(_build_otp_html(otp, purpose, expire_minutes), "html"))

    context = ssl.create_default_context()
    smtp_user = settings.SMTP_USERNAME.strip()
    smtp_pass = settings.SMTP_PASSWORD.replace(" ", "").strip()
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(settings.SMTP_FROM_EMAIL.strip(), to_email.strip(), msg.as_string())
        # OTP value is NOT logged here — security requirement
        print(f"[EMAIL] OTP email sent to {to_email} (purpose={purpose.value})")
    except smtplib.SMTPAuthenticationError:
        raise EmailDeliveryError(
            "SMTP authentication failed. Check SMTP_USERNAME and SMTP_PASSWORD in .env."
        )
    except smtplib.SMTPException as exc:
        raise EmailDeliveryError(f"SMTP error: {exc}")
    except OSError as exc:
        raise EmailDeliveryError(f"Network error sending email: {exc}")
