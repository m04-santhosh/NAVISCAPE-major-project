"""
Authentication Router
Password-based authentication with Gmail SMTP email OTP verification.
Handles multi-step registration (request OTP -> verify OTP -> user creation) and JWT session management.
"""

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..models.user import User
from ..schemas.user import (
    ForgotPasswordRequest,
    MessageResponse,
    RegisterOTPResponse,
    RegisterResendOTPRequest,
    RegisterVerifyOTPRequest,
    ResetPasswordRequest,
    TestEmailRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    VerifyOTPRequest,
)
from ..services.email_service import email_service, send_otp_email
from ..services.otp_service import (
    create_or_resend_otp,
    normalize_email,
    verify_and_consume_otp,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ── Registration / Signup with Email OTP Flow ──────────────────────────────────

@router.post("/register", response_model=RegisterOTPResponse, status_code=status.HTTP_200_OK)
@router.post("/signup", response_model=RegisterOTPResponse, status_code=status.HTTP_200_OK)
@router.post("/register/request-otp", response_model=RegisterOTPResponse, status_code=status.HTTP_200_OK)
async def register(
    data: UserRegister,
    db: Session = Depends(get_db),
):
    """
    Step 1 of Registration:
    Validates registration data, checks for duplicate email,
    generates a secure 6-digit OTP stored in the SQL database,
    and sends the OTP synchronously to the user's email via Gmail SMTP.
    Does NOT create the user record yet.
    """
    email = normalize_email(data.email)
    name = (data.full_name or data.name or "").strip()

    # Validate password confirmation
    if data.password != data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )

    # Check if email is already registered in SQL database
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please log in.",
        )

    # Generate 6-digit OTP and persist to SQL otp_records
    raw_otp, _ = create_or_resend_otp(db, email=email, purpose="SIGNUP", validity_minutes=10)

    # Send OTP email synchronously via Gmail SMTP
    mail_result = send_otp_email(
        to_email=email,
        otp=raw_otp,
        user_name=name or email.split("@")[0],
        purpose="Account Registration",
        validity_minutes=10,
    )

    if not mail_result.get("success", True):
        logger.error("[AUTH] Failed to send OTP email to %s: %s", email, mail_result.get("message"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mail_result.get("message", "Failed to send verification code. Please try again."),
        )

    return RegisterOTPResponse(
        status="otp_required",
        message="A 6-digit verification code has been sent to your email.",
        email=email,
        expires_in=600,
    )


@router.post("/register/verify-otp", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def verify_register_otp(
    data: RegisterVerifyOTPRequest,
    db: Session = Depends(get_db),
):
    """
    Step 2 of Registration:
    Validates 6-digit OTP against database records, consumes OTP,
    hashes password with bcrypt, creates the user record in the SQL database,
    and returns signed JWT access token.
    """
    email = normalize_email(data.email)
    name = (data.full_name or data.name or "").strip()

    # Validate password confirmation
    if data.password != data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )

    # Check if user was registered concurrently
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please log in.",
        )

    # Verify and consume OTP in database
    is_valid, msg = verify_and_consume_otp(db, email=email, otp=data.otp, purpose="SIGNUP")
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    hashed_pwd = hash_password(data.password)

    new_user = User(
        email=email,
        full_name=name or email.split("@")[0],
        username=email,
        hashed_password=hashed_pwd,
        pin_hash=hashed_pwd,
        email_verified=True,
        is_active=True,
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info("[AUTH] User registered and verified successfully (id=%s, email=%s)", new_user.id, email)
    except Exception as db_err:
        db.rollback()
        logger.error("[AUTH] User creation failed for email=%s: %s", email, db_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist user registration in database.",
        )

    token = create_access_token(data={"sub": str(new_user.id)})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(new_user),
    )


@router.post("/register/resend-otp", response_model=RegisterOTPResponse)
async def resend_register_otp(
    data: RegisterResendOTPRequest,
    db: Session = Depends(get_db),
):
    """
    Resend registration OTP:
    Invalidates any previous OTP, creates a fresh 6-digit OTP,
    and sends it via Gmail SMTP.
    """
    email = normalize_email(data.email)
    name = (data.full_name or data.name or "").strip()

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please log in.",
        )

    raw_otp, _ = create_or_resend_otp(db, email=email, purpose="SIGNUP", validity_minutes=10)

    mail_result = send_otp_email(
        to_email=email,
        otp=raw_otp,
        user_name=name or email.split("@")[0],
        purpose="Account Registration",
        validity_minutes=10,
    )

    if not mail_result.get("success", True):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=mail_result.get("message", "Failed to resend verification code. Please try again."),
        )

    return RegisterOTPResponse(
        status="otp_required",
        message="A new 6-digit verification code has been sent to your email.",
        email=email,
        expires_in=600,
    )


# ── Login Flow ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    db: Session = Depends(get_db),
):
    """
    Authenticate with email and password against the SQL users table.
    Returns a JWT access token and user information.
    """
    email = normalize_email(data.email)
    invalid_credentials_msg = "Invalid email or password."

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=invalid_credentials_msg,
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    # Verify password against hashed_password or pin_hash fallback
    stored_hash = user.hashed_password or user.pin_hash
    if not stored_hash or not verify_password(data.password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=invalid_credentials_msg,
        )

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


# ── Password Reset / Forgot Password Flow ─────────────────────────────────────

@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Send OTP code for password reset to registered user's email.
    """
    email = normalize_email(data.email)
    user = db.query(User).filter(User.email == email).first()

    # Always return success message for security (prevent email enumeration)
    if user:
        raw_otp, _ = create_or_resend_otp(db, email=email, purpose="FORGOT_PIN", validity_minutes=10)
        send_otp_email(
            to_email=email,
            otp=raw_otp,
            user_name=user.full_name,
            purpose="Password Reset",
            validity_minutes=10,
        )

    return MessageResponse(
        message="If an account exists with this email, a verification code has been sent."
    )


@router.post("/verify-otp", response_model=MessageResponse)
async def verify_otp_endpoint(
    data: VerifyOTPRequest,
    db: Session = Depends(get_db),
):
    """
    Verify an OTP code without consuming it immediately.
    """
    email = normalize_email(data.email)
    # Check if active OTP exists and matches
    is_valid, msg = verify_and_consume_otp(db, email=email, otp=data.otp, purpose="FORGOT_PIN")
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )
    return MessageResponse(message="OTP verified successfully.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Reset user password using a verified OTP.
    """
    email = normalize_email(data.email)

    if data.new_password != data.confirm_new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match.",
        )

    is_valid, msg = verify_and_consume_otp(db, email=email, otp=data.otp, purpose="FORGOT_PIN")
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    new_hash = hash_password(data.new_password)
    user.hashed_password = new_hash
    user.pin_hash = new_hash
    user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return MessageResponse(message="Password reset successfully. Please log in with your new password.")


# ── Change Password ────────────────────────────────────────────────────────────

@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change the authenticated user's password.
    Body: { current_password, new_password, confirm_new_password }
    """
    current_password = (data.get("current_password") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    confirm = (data.get("confirm_new_password") or "").strip()

    if not current_password or not new_password or not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="current_password, new_password, and confirm_new_password are required.",
        )
    if new_password != confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match.",
        )
    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters long.",
        )

    stored_hash = current_user.hashed_password or current_user.pin_hash
    if not stored_hash or not verify_password(current_password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    new_hash = hash_password(new_password)
    current_user.hashed_password = new_hash
    current_user.pin_hash = new_hash
    current_user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return MessageResponse(message="Password updated successfully.")


# ── Test Email Endpoint ────────────────────────────────────────────────────────

@router.post("/test-email", response_model=MessageResponse)
async def test_email_endpoint(
    data: TestEmailRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Send a test email via Gmail SMTP.
    Requires authentication.
    """
    recipient = normalize_email(data.recipient_email)
    result = email_service.send_email(
        to_email=recipient,
        subject=data.subject or "NAVISCAPE Test Email",
        body_text=data.message or "This is a test email sent from the NAVISCAPE backend via Gmail SMTP.",
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "Failed to send test email."),
        )

    return MessageResponse(message=f"Test email sent successfully to {recipient}.")


# ── Me / Profile ───────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    """Get current authenticated user profile. Requires valid JWT."""
    return UserResponse.model_validate(current_user)


# ── Logout ─────────────────────────────────────────────────────────────────────

@router.post("/logout", response_model=MessageResponse)
async def logout():
    """Client-side token disposal endpoint."""
    return MessageResponse(message="Logged out successfully.")
