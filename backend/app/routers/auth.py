"""
Authentication Router
Password-based authentication with JWT token management.
"""

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from ..config import settings
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
from ..email_service import email_service, otp_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


# ── Registration / Signup with Email OTP Flow ──────────────────────────────────

@router.post("/register", response_model=RegisterOTPResponse, status_code=status.HTTP_200_OK)
@router.post("/signup", response_model=RegisterOTPResponse, status_code=status.HTTP_200_OK)
@router.post("/register/request-otp", response_model=RegisterOTPResponse, status_code=status.HTTP_200_OK)
async def register(
    data: UserRegister,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Step 1 of Registration:
    Validates registration data, generates a secure 6-digit OTP,
    and sends the OTP to the user's email via Gmail SMTP.
    Does NOT create a permanent account yet.
    """
    email = _normalize_email(data.email)
    name = (data.full_name or data.name or "").strip()

    # Validate password confirmation
    if data.password != data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )

    # Check if email is already registered
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please log in.",
        )

    # Generate 6-digit OTP and store with 10-minute validity
    otp = otp_store.generate_otp(email=email, purpose="registration")

    # Send OTP email asynchronously via Gmail SMTP (non-blocking)
    if email_service.is_configured:
        background_tasks.add_task(
            email_service.send_otp_email,
            to_email=email,
            otp_code=otp,
            user_name=name or email.split("@")[0],
            purpose="Account Registration",
            validity_minutes=10,
        )
    else:
        logger.warning(
            "SMTP is not configured. Registration OTP generated for %s but could not be sent.",
            email,
        )

    return RegisterOTPResponse(
        status="otp_required",
        message="Verification code sent to your email. Please enter the 6-digit OTP to complete registration.",
        email=email,
    )


@router.post("/register/verify-otp", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@router.post("/verify-registration-otp", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def verify_registration_otp(
    data: RegisterVerifyOTPRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Step 2 of Registration:
    Verifies the 6-digit OTP code against OTPStore, and upon success,
    creates the permanent user account in the SQL database, hashes password with bcrypt,
    and returns a JWT authentication token.
    """
    email = _normalize_email(data.email)
    name = (data.full_name or data.name or "").strip()

    # Validate password confirmation
    if data.password != data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )

    # Check if email is already registered
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please log in.",
        )

    # Verify and consume OTP for registration
    is_valid, msg = otp_store.verify_otp(
        email=email,
        otp=data.otp,
        purpose="registration",
        consume=True,
    )
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
        logger.info(
            "[AUTH] Registration verification succeeded. SQLite user created successfully (id=%s, email=%s)",
            new_user.id,
            email,
        )
    except Exception as db_err:
        db.rollback()
        logger.error(
            "[AUTH] SQLite user creation failed for email=%s: %s",
            email,
            db_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist user registration in database.",
        )

    # Send welcome email asynchronously via BackgroundTasks (non-blocking)
    if email_service.is_configured:
        background_tasks.add_task(
            email_service.send_welcome_email,
            to_email=new_user.email,
            user_name=new_user.full_name,
        )

    token = create_access_token(data={"sub": str(new_user.id)})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(new_user),
    )


@router.post("/register/resend-otp", response_model=MessageResponse)
async def resend_registration_otp(
    data: RegisterResendOTPRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Resend registration 6-digit OTP code to the provided email.
    """
    email = _normalize_email(data.email)
    name = (data.full_name or data.name or "").strip()

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please log in.",
        )

    otp = otp_store.generate_otp(email=email, purpose="registration")

    if email_service.is_configured:
        background_tasks.add_task(
            email_service.send_otp_email,
            to_email=email,
            otp_code=otp,
            user_name=name or email.split("@")[0],
            purpose="Account Registration",
            validity_minutes=10,
        )

    return MessageResponse(
        message="A new verification code has been sent to your email address."
    )


# ── Password Reset / OTP Flow ──────────────────────────────────────────────────

@router.post("/forgot-password", response_model=MessageResponse)
@router.post("/forgot-pin", response_model=MessageResponse)
@router.post("/send-otp", response_model=MessageResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Generate and email a 6-digit OTP for password reset.
    Accepts email address and securely sends code via Gmail SMTP.
    """
    email = _normalize_email(data.email)
    user = db.query(User).filter(User.email == email).first()

    if not user:
        # Prevent user enumeration in responses while still returning a friendly message
        logger.info("Password reset requested for non-existent email: %s", email)
        return MessageResponse(
            message="If an account exists with this email, a verification code has been sent."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    # Generate 6-digit OTP and store with 10-minute validity
    otp = otp_store.generate_otp(email=email, purpose="password_reset")

    # Send OTP via Gmail SMTP in background
    if email_service.is_configured:
        background_tasks.add_task(
            email_service.send_otp_email,
            to_email=email,
            otp_code=otp,
            user_name=user.full_name,
            purpose="Password Reset",
            validity_minutes=10,
        )
    else:
        logger.warning(
            "SMTP is not configured. OTP generated for %s but could not be sent.",
            email,
        )

    return MessageResponse(
        message="A verification code has been sent to your email address."
    )


@router.post("/verify-otp", response_model=MessageResponse)
async def verify_otp(data: VerifyOTPRequest):
    """
    Verify an OTP code without consuming it immediately.
    """
    email = _normalize_email(data.email)
    is_valid, msg = otp_store.verify_otp(
        email=email,
        otp=data.otp,
        purpose="password_reset",
        consume=False,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )
    return MessageResponse(message="OTP verified successfully.")


@router.post("/reset-password", response_model=MessageResponse)
@router.post("/reset-pin", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Reset user password using a verified OTP.
    Validates OTP, consumes it, and updates password in the database.
    """
    email = _normalize_email(data.email)

    if data.new_password != data.confirm_new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match.",
        )

    # Verify and consume OTP
    is_valid, msg = otp_store.verify_otp(
        email=email,
        otp=data.otp,
        purpose="password_reset",
        consume=True,
    )
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


# ── Test Email Endpoint ────────────────────────────────────────────────────────

@router.post("/test-email", response_model=MessageResponse)
async def test_email(
    data: TestEmailRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Send a test email via Gmail SMTP.
    Requires authentication in production, or accessible in DEBUG mode.
    """
    recipient = _normalize_email(data.recipient_email)
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


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    db: Session = Depends(get_db),
):
    """
    Authenticate with email and password.
    Returns a JWT access token and user information.
    """
    email = _normalize_email(data.email)
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

