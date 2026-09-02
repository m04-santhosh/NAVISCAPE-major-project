"""
User Pydantic Schemas
Request/response validation for standard password-based authentication endpoints.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


# ── Auth Request Schemas ──────────────────────────────────────────────────────

class UserRegister(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    email: EmailStr
    password: str
    confirm_password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        return v

    @property
    def display_name(self) -> str:
        return (self.full_name or self.name or "").strip()


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()


# Backward compatibility aliases
RegisterRequest = UserRegister
LoginRequest = UserLogin


# ── Response Schemas ──────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    email_verified: bool = True
    is_active: bool = True
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


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None


# ── Password Reset & OTP Schemas ─────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
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

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v):
        cleaned = str(v).strip()
        if not cleaned:
            raise ValueError("OTP is required.")
        return cleaned


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str
    confirm_new_password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v):
        cleaned = str(v).strip()
        if not cleaned:
            raise ValueError("OTP is required.")
        return cleaned

    @field_validator("new_password")
    @classmethod
    def validate_new_password_length(cls, v):
        if len(v) < 6:
            raise ValueError("New password must be at least 6 characters long.")
        return v


class TestEmailRequest(BaseModel):
    recipient_email: EmailStr
    subject: Optional[str] = "NAVISCAPE Test Email"
    message: Optional[str] = None

    @field_validator("recipient_email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        return str(v).strip().lower()

