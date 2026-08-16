"""
Pydantic Schemas for Women Safety — Emergency Profile & Trusted Contacts
"""

import re
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator


# Standard Indian Mobile regex: allows optional +91 or 0 prefix followed by 10 digits starting with 6-9
INDIAN_MOBILE_REGEX = re.compile(r"^(?:\+91|0)?[6-9]\d{9}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def validate_indian_mobile(v: Optional[str]) -> Optional[str]:
    """Validate and clean Indian mobile number representation."""
    if v is None:
        return None
    cleaned = re.sub(r"[\s\-]", "", str(v).strip())
    if not cleaned:
        return None
    if not INDIAN_MOBILE_REGEX.match(cleaned):
        raise ValueError("Invalid Indian mobile number. Must be a valid 10-digit number starting with 6-9.")
    # Standardize to 10-digit representation
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]
    return cleaned


def validate_email_format(v: Optional[str]) -> Optional[str]:
    """Validate standard email format."""
    if v is None:
        return None
    cleaned = str(v).strip().lower()
    if not cleaned:
        return None
    if not EMAIL_REGEX.match(cleaned):
        raise ValueError("Invalid email format.")
    return cleaned


# ── Emergency Profile Schemas ──────────────────────────────────────────────────

class EmergencyProfileUpdate(BaseModel):
    emergency_mobile: Optional[str] = None
    emergency_email: Optional[str] = None
    location_sharing_consent: bool = False

    @field_validator("emergency_mobile")
    @classmethod
    def check_mobile(cls, v):
        return validate_indian_mobile(v)

    @field_validator("emergency_email")
    @classmethod
    def check_email(cls, v):
        return validate_email_format(v)


class EmergencyProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    emergency_mobile: Optional[str] = None
    emergency_email: Optional[str] = None
    location_sharing_consent: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Trusted Contact Schemas ───────────────────────────────────────────────────

class TrustedContactCreate(BaseModel):
    contact_name: str
    relationship: str
    mobile_number: str
    email: Optional[str] = None

    @field_validator("contact_name")
    @classmethod
    def check_name(cls, v):
        name = str(v).strip()
        if not name:
            raise ValueError("Contact name is required.")
        if len(name) > 100:
            raise ValueError("Contact name must not exceed 100 characters.")
        return name

    @field_validator("relationship")
    @classmethod
    def check_relationship(cls, v):
        rel = str(v).strip()
        if not rel:
            raise ValueError("Relationship is required.")
        if len(rel) > 50:
            raise ValueError("Relationship must not exceed 50 characters.")
        return rel

    @field_validator("mobile_number")
    @classmethod
    def check_mobile(cls, v):
        if not v:
            raise ValueError("Mobile number is required.")
        return validate_indian_mobile(v)

    @field_validator("email")
    @classmethod
    def check_email(cls, v):
        return validate_email_format(v)


class TrustedContactUpdate(BaseModel):
    contact_name: Optional[str] = None
    relationship: Optional[str] = None
    mobile_number: Optional[str] = None
    email: Optional[str] = None

    @field_validator("contact_name")
    @classmethod
    def check_name(cls, v):
        if v is None:
            return None
        name = str(v).strip()
        if not name:
            raise ValueError("Contact name cannot be empty.")
        if len(name) > 100:
            raise ValueError("Contact name must not exceed 100 characters.")
        return name

    @field_validator("relationship")
    @classmethod
    def check_relationship(cls, v):
        if v is None:
            return None
        rel = str(v).strip()
        if not rel:
            raise ValueError("Relationship cannot be empty.")
        if len(rel) > 50:
            raise ValueError("Relationship must not exceed 50 characters.")
        return rel

    @field_validator("mobile_number")
    @classmethod
    def check_mobile(cls, v):
        if v is None:
            return None
        return validate_indian_mobile(v)

    @field_validator("email")
    @classmethod
    def check_email(cls, v):
        return validate_email_format(v)


class TrustedContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    contact_name: str
    relationship: str
    mobile_number: str
    email: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Full Women Safety Overview / Profile Status ───────────────────────────────

class WomenSafetyOverviewResponse(BaseModel):
    emergency_profile: Optional[EmergencyProfileResponse] = None
    trusted_contacts: List[TrustedContactResponse] = []
    profile_complete: bool = False
    contacts_count: int = 0
    min_contacts_required: int = 2
    max_contacts_allowed: int = 4
    has_emergency_mobile: bool = False
    location_sharing_consent: bool = False
