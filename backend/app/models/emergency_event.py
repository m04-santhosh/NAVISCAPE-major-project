"""
NAVISCAPE Women Safety — Emergency Event ORM Model
Additive, secure model for user SOS emergency sessions.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from ..database import Base


class EmergencyEvent(Base):
    """
    Emergency event entity associated with a User.
    Stores the emergency trigger status, captured GPS coordinates, accuracy,
    and server timestamps.
    """
    __tablename__ = "emergency_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)  # ACTIVE, CANCELLED
    triggered_at = Column(DateTime, server_default=func.now(), nullable=False)
    cancelled_at = Column(DateTime, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_accuracy_m = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="emergency_events")

    def __repr__(self):
        return (
            f"<EmergencyEvent(id={self.id}, user_id={self.user_id}, "
            f"status='{self.status}', lat={self.latitude}, lng={self.longitude})>"
        )
