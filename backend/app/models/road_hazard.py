"""
Road Hazard ORM Model
Stores real-time road hazard reports submitted by authenticated users.
"""

from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from ..database import Base


class RoadHazard(Base):
    __tablename__ = "road_hazards"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    hazard_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    status = Column(String(20), default="Active", nullable=False, index=True)  # Active / Resolved

    # Relationship to user
    user = relationship("User")

    def __repr__(self):
        return f"<RoadHazard(id={self.id}, type='{self.hazard_type}', severity='{self.severity}', status='{self.status}')>"
