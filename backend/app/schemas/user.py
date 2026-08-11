"""
User Pydantic Schemas
Request/response validation for authentication endpoints.
Email + PIN authentication — no username, no password fields.
"""

import re
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime


# ── Validators ────────────────────────────────────────────────────────────────

def _validate_pin(pin: str) -> str:
    """PIN must be 4–6 digits, numeric only."""
    if not re.fullmatch(r"\d{4,6}", pin):
        raise ValueError("PIN must be 4–6 digits (numbers only).")
    return pin


# ── Signup Schemas ────────────────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()

    @field_validator("otp", mode="before")
    @classmethod
    def validate_otp_format(cls, v):
        v = str(v).strip()
        if not re.fullmatch(r"\d{6}", v):
            raise ValueError("Verification code must be 6 digits.")
        return v


class SetPINRequest(BaseModel):
    email: EmailStr
    verification_token: str
    pin: str
    confirm_pin: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v):
        return _validate_pin(v)

    @field_validator("confirm_pin")
    @classmethod
    def validate_confirm_pin(cls, v):
        return _validate_pin(v)


# ── Login Schema ──────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    pin: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()


# ── Forgot PIN Schemas ────────────────────────────────────────────────────────

class ForgotPINSendOTPRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()


class ForgotPINVerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()

    @field_validator("otp", mode="before")
    @classmethod
    def validate_otp_format(cls, v):
        v = str(v).strip()
        if not re.fullmatch(r"\d{6}", v):
            raise ValueError("Verification code must be 6 digits.")
        return v


class ForgotPINResetRequest(BaseModel):
    email: EmailStr
    verification_token: str
    new_pin: str
    confirm_pin: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()

    @field_validator("new_pin")
    @classmethod
    def validate_pin(cls, v):
        return _validate_pin(v)

    @field_validator("confirm_pin")
    @classmethod
    def validate_confirm_pin(cls, v):
        return _validate_pin(v)


# ── Response Schemas ──────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: int
    email: str
    email_verified: bool
    is_active: bool
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class MessageResponse(BaseModel):
    message: str


class VerificationTokenResponse(BaseModel):
    """Returned after OTP verification — caller uses this to complete the flow."""
    verification_token: str
    message: str


# ── Legacy schemas (kept to avoid import errors in unchanged routers) ─────────
# These are no longer used by new auth endpoints.

class UserRegister(BaseModel):
    username: str = ""
    email: EmailStr = ""
    password: str = ""
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str = ""
    password: str = ""


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
