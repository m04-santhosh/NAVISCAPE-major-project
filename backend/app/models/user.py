"""
User ORM Model
Email + PIN authentication. Legacy columns (username, hashed_password, full_name, is_admin)
are kept in the SQLite schema for backward compatibility but are NOT used by the new auth system.
New columns are added via additive ALTER TABLE migration in database.py.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.orm import relationship
from ..database import Base


class User(Base):
    __tablename__ = "users"

    # ── Primary key ──────────────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # ── New auth fields (added via ALTER TABLE migration) ────────────────────
    email = Column(String(254), unique=True, nullable=False, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    pin_hash = Column(String(255), nullable=True)          # nullable until PIN is set
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime, nullable=True)

    # ── Legacy columns (preserved for migration compatibility, unused) ────────
    # These columns exist in the old schema and are kept to avoid breaking
    # the existing SQLite table. They are NOT read or written by new code.
    # username, hashed_password, full_name, is_admin — defined below as nullable
    username = Column(String(50), nullable=True, index=True)
    hashed_password = Column(String(255), nullable=True)
    full_name = Column(String(100), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    route_history = relationship("RouteHistory", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', verified={self.email_verified})>"
