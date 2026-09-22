"""
NAVISCAPE Database-Backed OTP Service
Handles cryptographically secure OTP generation, SHA-256 hashing,
expiration, attempt limiting, and one-time verification using the SQL database.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from typing import Tuple, Optional
from sqlalchemy.orm import Session

from ..models.otp import OTPRecord, OTPPurpose

logger = logging.getLogger("naviscape.otp_service")

OTP_EXPIRY_MINUTES = 10
MAX_VERIFICATION_ATTEMPTS = 5


def normalize_email(email: str) -> str:
    """Consistently trim whitespace and lowercase email strings."""
    return email.strip().lower()


def hash_otp(email: str, otp: str) -> str:
    """Generate SHA-256 hex digest for an OTP salted with normalized email."""
    norm_email = normalize_email(email)
    payload = f"{norm_email}:{otp.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def generate_secure_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


def create_or_resend_otp(
    db: Session,
    email: str,
    purpose: str = "SIGNUP",
    validity_minutes: int = OTP_EXPIRY_MINUTES,
) -> Tuple[str, OTPRecord]:
    """
    Invalidates any previous active OTPs for the user and purpose,
    generates a new 6-digit OTP, stores its SHA-256 hash in SQL, and returns (raw_otp, record).
    """
    norm_email = normalize_email(email)

    # Invalidate any previous unverified OTPs for this email and purpose
    db.query(OTPRecord).filter(
        OTPRecord.email == norm_email,
        OTPRecord.purpose == purpose,
        OTPRecord.verified == False,
    ).update({"verified": True})

    raw_otp = generate_secure_otp(6)
    hashed_otp = hash_otp(norm_email, raw_otp)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + timedelta(minutes=validity_minutes)

    otp_record = OTPRecord(
        email=norm_email,
        otp_hash=hashed_otp,
        purpose=purpose,
        expires_at=expires_at,
        attempts=0,
        verified=False,
        created_at=now,
    )

    db.add(otp_record)
    db.commit()
    db.refresh(otp_record)

    logger.info(
        "[OTP] Generated new OTP (id=%s) for email=%s, purpose=%s, expires_at=%s",
        otp_record.id,
        norm_email,
        purpose,
        expires_at,
    )
    return raw_otp, otp_record


def verify_and_consume_otp(
    db: Session,
    email: str,
    otp: str,
    purpose: str = "SIGNUP",
) -> Tuple[bool, str]:
    """
    Locates the active OTP record from SQL, validates expiry and attempt limits,
    verifies the hash, and consumes (invalidates) the OTP upon success.
    Returns (is_valid, message).
    """
    norm_email = normalize_email(email)
    raw_otp = otp.strip()

    # Locate the latest unverified OTP record
    record = (
        db.query(OTPRecord)
        .filter(
            OTPRecord.email == norm_email,
            OTPRecord.purpose == purpose,
            OTPRecord.verified == False,
        )
        .order_by(OTPRecord.id.desc())
        .first()
    )

    if not record:
        return False, "No active verification code found. Please request a new code."

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Check expiration
    if now > record.expires_at:
        record.verified = True  # Invalidate expired record
        db.commit()
        return False, "Verification code has expired. Please request a new code."

    # Check attempt limit before checking password
    if record.attempts >= MAX_VERIFICATION_ATTEMPTS:
        record.verified = True  # Invalidate burned record
        db.commit()
        return False, "Too many failed attempts. Please request a new verification code."

    # Increment attempts
    record.attempts += 1
    computed_hash = hash_otp(norm_email, raw_otp)

    # Secure constant-time comparison
    if secrets.compare_digest(record.otp_hash, computed_hash):
        record.verified = True  # One-time use: consume OTP
        db.commit()
        logger.info("[OTP] Successfully verified & consumed OTP for email=%s", norm_email)
        return True, "Verification code verified successfully."

    # Failed attempt
    remaining = MAX_VERIFICATION_ATTEMPTS - record.attempts
    if remaining <= 0:
        record.verified = True  # Invalidate if attempts exhausted
        db.commit()
        return False, "Invalid verification code. Maximum attempts reached. Please request a new code."

    db.commit()
    return False, f"Invalid verification code. {remaining} attempt(s) remaining."
