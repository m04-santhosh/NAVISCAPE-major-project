"""
NAVISCAPE Women Safety — Emergency Action Audit Trail ORM Model
Stores chronological audit log of actions taken during an emergency session.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from ..database import Base


class EmergencyAction(Base):
    """
    Emergency action entity recorded during an emergency session.
    Represents discrete orchestration steps (e.g. SOS_ACTIVATED, GPS_CAPTURED,
    WHATSAPP_OPENED, ALERT_SENT_CONFIRMED, EMERGENCY_RESOLVED).
    """
    __tablename__ = "emergency_actions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    emergency_event_id = Column(Integer, ForeignKey("emergency_events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False, index=True)
    contact_type = Column(String(50), nullable=True)  # PRIMARY, TRUSTED, POLICE, EMERGENCY
    contact_name = Column(String(100), nullable=True)
    contact_phone = Column(String(30), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    metadata_json = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", backref="emergency_actions")
    emergency_event = relationship("EmergencyEvent", backref="actions")

    def __repr__(self):
        return (
            f"<EmergencyAction(id={self.id}, event_id={self.emergency_event_id}, "
            f"user_id={self.user_id}, type='{self.action_type}')>"
        )
