"""
Authentication Router
Password-based authentication with JWT token management.
Direct email + password registration and login without external email/OTP dependencies.
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
    MessageResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


# ── Registration / Signup Flow ────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    db: Session = Depends(get_db),
):
    """
    Direct user registration with email and password.
    1. Validates registration data and password matching.
    2. Checks whether the email is already registered in the SQL database.
    3. Hashes the password using bcrypt.
    4. Creates and commits the user record directly in the SQL users table.
    5. Generates a signed JWT access token.
    6. Returns the JWT token and user profile immediately.
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
            "[AUTH] User registered successfully (id=%s, email=%s)",
            new_user.id,
            email,
        )
    except Exception as db_err:
        db.rollback()
        logger.error(
            "[AUTH] User creation failed for email=%s: %s",
            email,
            db_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist user registration in database.",
        )

    token = create_access_token(data={"sub": str(new_user.id)})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(new_user),
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

