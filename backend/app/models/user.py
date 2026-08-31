"""
User ORM Model
Password-based authentication.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.orm import relationship
from ..database import Base


class User(Base):
    __tablename__ = "users"

    # ── Primary key ──────────────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # ── Core fields ──────────────────────────────────────────────────────────
    email = Column(String(254), unique=True, nullable=False, index=True)
    full_name = Column(String(100), nullable=True)
    username = Column(String(50), nullable=True, index=True)
    hashed_password = Column(String(255), nullable=True)
    email_verified = Column(Boolean, default=True, nullable=False)
    pin_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    route_history = relationship("RouteHistory", back_populates="user", cascade="all, delete-orphan")
    emergency_profile = relationship("EmergencyProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    trusted_contacts = relationship("TrustedContact", back_populates="user", cascade="all, delete-orphan")
    emergency_events = relationship("EmergencyEvent", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', name='{self.full_name}')>"
