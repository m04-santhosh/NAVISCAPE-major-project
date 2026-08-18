"""
NAVISCAPE Women Safety — Emergency Profile & Trusted Contacts ORM Models
Provides additive, secure models for user emergency profile and trusted contacts.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship as orm_relationship
from ..database import Base


class EmergencyProfile(Base):
    """
    Emergency profile entity associated 1-to-1 with a User.
    Stores emergency phone, optional email, and explicit location-sharing consent.
    """
    __tablename__ = "emergency_profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    emergency_mobile = Column(String(20), nullable=True)
    emergency_email = Column(String(254), nullable=True)
    location_sharing_consent = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = orm_relationship("User", back_populates="emergency_profile")

    def __repr__(self):
        return f"<EmergencyProfile(id={self.id}, user_id={self.user_id}, consent={self.location_sharing_consent})>"


class TrustedContact(Base):
    """
    Trusted contact entity associated 1-to-many with a User (max 4).
    Stores contact name, relationship, phone, and optional email.
    """
    __tablename__ = "trusted_contacts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_name = Column(String(100), nullable=False)
    relationship = Column(String(50), nullable=False)
    mobile_number = Column(String(20), nullable=False)
    email = Column(String(254), nullable=True)
    whatsapp_number = Column(String(20), nullable=True, default=None)
    whatsapp_alert_consent = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = orm_relationship("User", back_populates="trusted_contacts")

    def __repr__(self):
        return f"<TrustedContact(id={self.id}, user_id={self.user_id}, name='{self.contact_name}', rel='{self.relationship}')>"
