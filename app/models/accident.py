"""
Accident Data ORM Model
Stores accident records with location, severity, and conditions.
"""

from sqlalchemy import Column, Integer, Float, String, DateTime, Text, func
from ..database import Base


class AccidentData(Base):
    __tablename__ = "accident_data"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    severity = Column(Integer, nullable=True)  # 1 (minor) to 5 (fatal)
    timestamp = Column(DateTime, nullable=True)
    weather_condition = Column(String(50), nullable=True)  # clear, rain, fog, etc.
    road_condition = Column(String(50), nullable=True)  # dry, wet, icy, etc.
    description = Column(Text, nullable=True)
    casualties = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<AccidentData(id={self.id}, severity={self.severity}, loc=({self.latitude},{self.longitude}))>"
