"""
JWT Authentication Middleware
Handles token creation, verification, and user extraction.
All protected endpoints derive identity from a verified JWT — no hardcoded users.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..firebase import verify_firebase_id_token

# PIN hashing — bcrypt via passlib (same library already in requirements.txt)
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme — extracts Bearer token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# ── Password Hashing (bcrypt via passlib) ─────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    if not hashed_password:
        return False
    return _pwd_context.verify(plain_password, hashed_password)


# Aliases for backward compatibility
hash_pin = hash_password
verify_pin = verify_password


# ── JWT token management ──────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "iss": "naviscape",
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token. Returns payload dict or None on failure."""
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except JWTError:
        return None


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: extract, verify Firebase ID token (or legacy JWT), look up user.

    1. Attempts Firebase ID Token verification via Firebase Admin SDK.
    2. Falls back to signed JWT verification for existing tests and transitional sessions.
    3. Finds or auto-syncs user entity and verifies account is active.

    Raises HTTP 401 for any authentication failure.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    # 1. Try Firebase ID Token Verification
    fb_payload = verify_firebase_id_token(token)
    if fb_payload:
        uid = fb_payload.get("uid")
        email = fb_payload.get("email")
        if not email and uid:
            email = f"{uid}@firebase.naviscape"

        # Sync Firestore user document
        from ..repositories.firestore_repo import firestore_repo
        if firestore_repo.db:
            fs_user = firestore_repo.get_user_by_uid(uid)
            if not fs_user:
                firestore_repo.create_or_update_user(
                    uid,
                    {
                        "email": email,
                        "full_name": fb_payload.get("name") or (email.split("@")[0] if email else "User"),
                        "username": email.split("@")[0] if email else "user",
                        "email_verified": fb_payload.get("email_verified", True),
                        "is_active": True,
                    },
                )

        # Lookup user by email in current database layer
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            # Auto-provision local record for Firebase authenticated user
            user = User(
                email=email,
                full_name=fb_payload.get("name") or (email.split("@")[0] if email else "User"),
                username=email.split("@")[0] if email else "user",
                email_verified=fb_payload.get("email_verified", True),
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated.",
            )
        return user


    # 2. Fallback to standard signed JWT Token Verification
    payload = _decode_token(token)
    if payload is None:
        raise credentials_exception

    user_id_str: Optional[str] = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
        user = db.query(User).filter(User.id == user_id).first()
    except (ValueError, TypeError):
        # In case sub was an email or string UID
        user = db.query(User).filter(User.email == str(user_id_str)).first()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    return user


async def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    FastAPI dependency: returns current user or None (no error if unauthenticated).
    Used for endpoints that behave differently for authenticated vs. guest users.
    """
    if not token:
        return None
    try:
        return await get_current_user(token=token, db=db)
    except HTTPException:
        return None

