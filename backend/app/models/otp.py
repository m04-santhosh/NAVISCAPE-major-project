"""
OTP ORM Model
Stores hashed one-time passwords for email verification and PIN reset flows.
OTP values are NEVER stored in plaintext.
"""

from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, func
from ..database import Base


class OTPPurpose(str, PyEnum):
    SIGNUP = "SIGNUP"
    FORGOT_PIN = "FORGOT_PIN"


class OTPRecord(Base):
    __tablename__ = "otp_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(254), nullable=False, index=True)
    otp_hash = Column(String(64), nullable=False)          # SHA-256 hex digest
    purpose = Column(Enum(OTPPurpose), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<OTPRecord(id={self.id}, email='{self.email}', purpose={self.purpose}, verified={self.verified})>"
