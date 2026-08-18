"""
Authentication Router
Email + PIN authentication with OTP verification.

Flow:
  Signup:     send-signup-otp → verify-signup-otp → set-pin → (JWT issued)
  Login:      POST /login (email + PIN → JWT)
  Forgot PIN: forgot-pin/send-otp → forgot-pin/verify-otp → forgot-pin/reset

Security:
  - OTP values are NEVER returned in API responses
  - JWT subject is user.id (integer, not email)
  - PIN is bcrypt-hashed before storage
  - Forgot PIN always returns a generic message (doesn't reveal account existence)
  - User identity for protected endpoints comes from JWT, not request body
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..middleware.auth import create_access_token, get_current_user, hash_pin, verify_pin
from ..models.otp import OTPPurpose
from ..models.user import User
from ..schemas.user import (
    ForgotPINResetRequest,
    ForgotPINSendOTPRequest,
    ForgotPINVerifyOTPRequest,
    LoginRequest,
    MessageResponse,
    SendOTPRequest,
    SetPINRequest,
    TokenResponse,
    UserResponse,
    VerificationTokenResponse,
    VerifyOTPRequest,
)
from ..services.email_service import EmailDeliveryError, send_otp_email
from ..services.otp_service import (
    OTPError,
    send_otp,
    validate_verification_token,
    verify_otp,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _get_client_ip(request: Request) -> str:
    """Extract the best-available client IP from the request headers or connection."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip and cf_ip.strip():
        return cf_ip.strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for and forwarded_for.strip():
        return forwarded_for.split(",")[0].strip()

    return request.client.host if (request.client and request.client.host) else "unknown"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


# ── Signup ─────────────────────────────────────────────────────────────────────

@router.post("/send-signup-otp", response_model=MessageResponse)
async def send_signup_otp(
    data: SendOTPRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Step 1 of signup.
    Sends a 6-digit OTP to the user's email.
    Does NOT reveal whether the email is already registered.
    """
    email = _normalize_email(data.email)
    client_ip = _get_client_ip(request)

    # Check if email is already registered and verified
    existing = db.query(User).filter(User.email == email).first()
    if existing and existing.email_verified and existing.pin_hash:
        # Don't reveal this — return same generic message
        return MessageResponse(message="If this email is not registered, a verification code has been sent.")

    try:
        otp_plain = send_otp(db, email, OTPPurpose.SIGNUP, client_ip)
    except OTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    try:
        send_otp_email(email, otp_plain, OTPPurpose.SIGNUP)
    except EmailDeliveryError as exc:
        if settings.DEBUG:
            print(f"[DEV MODE] SMTP not configured. OTP code for {email} is: {otp_plain}")
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            )

    return MessageResponse(
        message="If this email is not registered, a verification code has been sent."
    )


@router.post("/verify-signup-otp", response_model=VerificationTokenResponse)
async def verify_signup_otp(
    data: VerifyOTPRequest,
    db: Session = Depends(get_db),
):
    """
    Step 2 of signup.
    Verifies the OTP and returns a short-lived verification token.
    The token is required for the set-pin step.
    """
    email = _normalize_email(data.email)

    try:
        token = verify_otp(db, email, data.otp, OTPPurpose.SIGNUP)
    except OTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return VerificationTokenResponse(
        verification_token=token,
        message="Email verified. Please set your PIN to complete registration.",
    )


@router.post("/set-pin", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def set_pin(
    data: SetPINRequest,
    db: Session = Depends(get_db),
):
    """
    Step 3 of signup.
    Creates the user account (or activates pending account) and sets the PIN.
    Requires a valid verification token from verify-signup-otp.
    Returns a JWT to immediately authenticate the new user.
    """
    email = _normalize_email(data.email)

    # Validate verification token
    try:
        validate_verification_token(data.verification_token, email, OTPPurpose.SIGNUP.value)
    except OTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    # Validate PIN match
    if data.pin != data.confirm_pin:
        raise HTTPException(status_code=400, detail="PINs do not match.")

    # Create or update user
    user = db.query(User).filter(User.email == email).first()
    if user and user.email_verified and user.pin_hash:
        raise HTTPException(
            status_code=400,
            detail="An account with this email already exists. Please log in.",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if user is None:
        user = User(
            email=email,
            username=email,
            hashed_password="",
            email_verified=True,
            pin_hash=hash_pin(data.pin),
            is_active=True,
            last_login_at=now,
        )
        db.add(user)
    else:
        # Pending user (email not yet verified or PIN not set)
        user.email_verified = True
        user.pin_hash = hash_pin(data.pin)
        user.is_active = True
        user.last_login_at = now

    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Authenticate with email + PIN.
    Returns a JWT access token and basic user information.
    Error messages are intentionally generic to prevent user enumeration.
    """
    email = _normalize_email(data.email)
    _invalid = "Invalid email or PIN."

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_invalid)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email address not verified. Please complete sign-up.",
        )

    if not user.pin_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_invalid)

    if not verify_pin(data.pin, user.pin_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_invalid)

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


# ── Me / Profile ───────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    """Get the current authenticated user's profile. Requires valid JWT."""
    return UserResponse.model_validate(current_user)


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """
    Logout endpoint. JWT invalidation is handled client-side (token deletion).
    Returns 200 so the client can cleanly complete the logout flow.
    """
    return MessageResponse(message="Logged out successfully.")


# ── Forgot PIN ─────────────────────────────────────────────────────────────────

_FORGOT_PIN_GENERIC = "If the account exists, a verification code has been sent."


@router.post("/forgot-pin/send-otp", response_model=MessageResponse)
async def forgot_pin_send_otp(
    data: ForgotPINSendOTPRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Step 1 of PIN reset.
    Always returns the same generic response — does NOT reveal account existence.
    """
    email = _normalize_email(data.email)
    client_ip = _get_client_ip(request)

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.email_verified or not user.pin_hash:
        # No account — return generic message without error
        return MessageResponse(message=_FORGOT_PIN_GENERIC)

    try:
        otp_plain = send_otp(db, email, OTPPurpose.FORGOT_PIN, client_ip)
    except OTPError as exc:
        if exc.status_code == 429:
            raise HTTPException(status_code=429, detail=exc.message)
        return MessageResponse(message=_FORGOT_PIN_GENERIC)

    try:
        send_otp_email(email, otp_plain, OTPPurpose.FORGOT_PIN)
    except EmailDeliveryError as exc:
        if settings.DEBUG:
            print(f"[DEV MODE] SMTP not configured. OTP code for {email} is: {otp_plain}")
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            )

    return MessageResponse(message=_FORGOT_PIN_GENERIC)


@router.post("/forgot-pin/verify-otp", response_model=VerificationTokenResponse)
async def forgot_pin_verify_otp(
    data: ForgotPINVerifyOTPRequest,
    db: Session = Depends(get_db),
):
    """
    Step 2 of PIN reset.
    Verifies the OTP and returns a short-lived reset token.
    """
    email = _normalize_email(data.email)

    try:
        token = verify_otp(db, email, data.otp, OTPPurpose.FORGOT_PIN)
    except OTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return VerificationTokenResponse(
        verification_token=token,
        message="Verified. Please enter your new PIN.",
    )


@router.post("/forgot-pin/reset", response_model=MessageResponse)
async def forgot_pin_reset(
    data: ForgotPINResetRequest,
    db: Session = Depends(get_db),
):
    """
    Step 3 of PIN reset.
    Validates the reset token, verifies PIN match, and updates the PIN hash.
    The old PIN stops working immediately.
    """
    email = _normalize_email(data.email)

    try:
        validate_verification_token(data.verification_token, email, OTPPurpose.FORGOT_PIN.value)
    except OTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    if data.new_pin != data.confirm_pin:
        raise HTTPException(status_code=400, detail="PINs do not match.")

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request.",
        )

    user.pin_hash = hash_pin(data.new_pin)
    user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return MessageResponse(message="PIN updated successfully. Please log in with your new PIN.")
