"""
OTP Service
Secure one-time password generation, hashing, verification, and rate limiting.

Security properties:
- OTP values are NEVER stored in plaintext (SHA-256 hashed)
- OTP values are NEVER logged or returned in API responses
- Each OTP is single-use
- Configurable expiry (default 5 minutes)
- Maximum verification attempts (default 5)
- Resend cooldown (default 60 seconds)
- Per-email rate limit (default 5 OTPs/hour)
- Per-IP rate limit (default 10 OTPs/hour) — in-memory, cleared hourly
"""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from ..config import settings
from ..models.otp import OTPRecord, OTPPurpose

# ── In-memory IP rate limit tracker ──────────────────────────────────────────
# Maps client_ip -> list of Unix timestamps for OTP requests in the last hour
_ip_request_log: dict[str, list] = defaultdict(list)


def _clean_ip_log():
    """Remove timestamps older than 1 hour from the in-memory log."""
    cutoff = time.monotonic() - 3600
    for ip in list(_ip_request_log.keys()):
        _ip_request_log[ip] = [t for t in _ip_request_log[ip] if t > cutoff]
        if not _ip_request_log[ip]:
            del _ip_request_log[ip]


def _check_ip_rate_limit(client_ip: str) -> bool:
    """Returns True if IP is within allowed limit, False if rate-limited."""
    _clean_ip_log()
    count = len(_ip_request_log.get(client_ip, []))
    return count < settings.OTP_MAX_PER_IP_PER_HOUR


def _record_ip_request(client_ip: str):
    """Record an OTP request for this IP."""
    _ip_request_log[client_ip].append(time.monotonic())


# ── OTP helpers ───────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP string."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_otp(otp: str) -> str:
    """Return SHA-256 hex digest of the OTP string."""
    return hashlib.sha256(otp.encode()).hexdigest()


def _normalize_email(email: str) -> str:
    """Lowercase and strip whitespace from email."""
    return email.strip().lower()


# ── Verification / reset token helpers ────────────────────────────────────────

def _generate_verification_token(email: str, purpose: str) -> str:
    """
    Generate a short-lived HMAC-based verification token.
    Encodes: email | purpose | unix_timestamp | random nonce
    """
    nonce = secrets.token_hex(16)
    ts = int(time.time())
    message = f"{email}|{purpose}|{ts}|{nonce}"
    sig = hmac.new(settings.SECRET_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()
    # Token format: base64-url-safe encoded payload + signature
    import base64
    payload = base64.urlsafe_b64encode(message.encode()).decode()
    return f"{payload}.{sig}"


def _verify_token(token: str, expected_email: str, expected_purpose: str) -> Tuple[bool, str]:
    """
    Validate a verification token.
    Returns (is_valid, error_message).
    """
    import base64
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False, "Invalid token format."
        payload_b64, provided_sig = parts
        message = base64.urlsafe_b64decode(payload_b64 + "==").decode()
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            return False, "Invalid token signature."

        fields = message.split("|")
        if len(fields) != 4:
            return False, "Malformed token."
        email, purpose, ts_str, _ = fields

        if _normalize_email(email) != _normalize_email(expected_email):
            return False, "Token email mismatch."
        if purpose != expected_purpose:
            return False, "Token purpose mismatch."

        ts = int(ts_str)
        if time.time() - ts > settings.VERIFICATION_TOKEN_EXPIRE_SECONDS:
            return False, "Verification token has expired. Please restart the process."

        return True, ""
    except Exception:
        return False, "Invalid token."


# ── Core OTP service functions ────────────────────────────────────────────────

class OTPError(Exception):
    """Raised when OTP operation fails with a user-safe message."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def send_otp(
    db: Session,
    email: str,
    purpose: OTPPurpose,
    client_ip: str = "unknown",
) -> str:
    """
    Create a new OTP for the given email and purpose.

    Enforces:
    - IP rate limit
    - Per-email hourly limit
    - Resend cooldown (60 seconds)
    - Invalidates previous OTPs for same email+purpose

    Returns the plaintext OTP (caller must send it by email, NOT log it).
    Raises OTPError on rate limit or abuse.
    """
    email = _normalize_email(email)
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    cooldown_threshold = now - timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS)

    # ── IP rate limit check ───────────────────────────────────────────────────
    if not _check_ip_rate_limit(client_ip):
        raise OTPError(
            "Too many requests from this network. Please try again later.",
            status_code=429,
        )

    # ── Per-email hourly limit ────────────────────────────────────────────────
    email_count_this_hour = (
        db.query(OTPRecord)
        .filter(
            OTPRecord.email == email,
            OTPRecord.purpose == purpose,
            OTPRecord.created_at >= one_hour_ago.replace(tzinfo=None),
        )
        .count()
    )
    if email_count_this_hour >= settings.OTP_MAX_PER_EMAIL_PER_HOUR:
        raise OTPError(
            "Too many verification requests for this email. Please wait before trying again.",
            status_code=429,
        )

    # ── Resend cooldown check ─────────────────────────────────────────────────
    latest = (
        db.query(OTPRecord)
        .filter(
            OTPRecord.email == email,
            OTPRecord.purpose == purpose,
            OTPRecord.verified == False,
        )
        .order_by(OTPRecord.created_at.desc())
        .first()
    )
    if latest and latest.created_at and latest.created_at > cooldown_threshold.replace(tzinfo=None):
        remaining = settings.OTP_RESEND_COOLDOWN_SECONDS - int(
            (now.replace(tzinfo=None) - latest.created_at).total_seconds()
        )
        raise OTPError(
            f"Please wait {max(0, remaining)} seconds before requesting a new code.",
            status_code=429,
        )

    # ── Invalidate previous OTPs for this email+purpose ──────────────────────
    db.query(OTPRecord).filter(
        OTPRecord.email == email,
        OTPRecord.purpose == purpose,
        OTPRecord.verified == False,
    ).delete(synchronize_session=False)

    # ── Generate and store new OTP ────────────────────────────────────────────
    otp_plain = _generate_otp()
    otp_hash = _hash_otp(otp_plain)
    expires_at = now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

    record = OTPRecord(
        email=email,
        otp_hash=otp_hash,
        purpose=purpose,
        expires_at=expires_at.replace(tzinfo=None),
        attempts=0,
        verified=False,
    )
    db.add(record)
    db.commit()

    # Record IP usage AFTER successful DB write
    _record_ip_request(client_ip)

    # Return plaintext OTP — caller sends it by email, must NOT log it
    return otp_plain


def verify_otp(
    db: Session,
    email: str,
    otp_plain: str,
    purpose: OTPPurpose,
) -> str:
    """
    Verify an OTP for the given email and purpose.

    Returns a short-lived verification token on success.
    Raises OTPError on failure (expired, invalid, max attempts exceeded).
    """
    email = _normalize_email(email)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    record = (
        db.query(OTPRecord)
        .filter(
            OTPRecord.email == email,
            OTPRecord.purpose == purpose,
            OTPRecord.verified == False,
        )
        .order_by(OTPRecord.created_at.desc())
        .first()
    )

    # Generic message — don't reveal whether the record exists
    _invalid_msg = "Invalid or expired verification code."

    if record is None:
        raise OTPError(_invalid_msg)

    # Check expiry
    if record.expires_at < now:
        db.delete(record)
        db.commit()
        raise OTPError(_invalid_msg)

    # Check attempt limit
    if record.attempts >= settings.OTP_MAX_ATTEMPTS:
        db.delete(record)
        db.commit()
        raise OTPError(
            "Too many incorrect attempts. Please request a new verification code.",
            status_code=429,
        )

    # Verify hash
    provided_hash = _hash_otp(otp_plain)
    if not hmac.compare_digest(provided_hash, record.otp_hash):
        record.attempts += 1
        db.commit()
        remaining = settings.OTP_MAX_ATTEMPTS - record.attempts
        raise OTPError(
            f"Invalid or expired verification code." +
            (f" {remaining} attempt(s) remaining." if remaining > 0 else ""),
        )

    # Success — mark as verified and return a verification token
    record.verified = True
    db.commit()

    token = _generate_verification_token(email, purpose.value)
    return token


def validate_verification_token(token: str, email: str, purpose: str) -> None:
    """
    Validate a verification token. Raises OTPError on failure.
    """
    is_valid, error = _verify_token(token, email, purpose)
    if not is_valid:
        raise OTPError(error, status_code=400)
