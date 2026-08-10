"""
Accident Data ORM Model — Karnataka Dataset Schema
Stores historical accident records with all fields from the Karnataka Accident Dataset.
"""

from sqlalchemy import Column, Integer, Float, String, DateTime, Text, func
from ..database import Base


class AccidentData(Base):
    __tablename__ = "accident_data"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Source identification
    district = Column(String(100), nullable=True, index=True)
    police_station = Column(String(200), nullable=True)
    crime_no = Column(String(100), nullable=True, index=True)


    # Accident details
    year = Column(Integer, nullable=True, index=True)
    vehicles_involved = Column(Integer, nullable=True)
    classification = Column(String(200), nullable=True)
    accident_spot = Column(String(200), nullable=True)
    accident_location = Column(Text, nullable=True)
    main_cause = Column(String(200), nullable=True, index=True)
    hit_run = Column(String(20), nullable=True)
    severity = Column(String(100), nullable=True, index=True)

    # Road & environmental conditions
    collision_type = Column(String(100), nullable=True)
    junction_control = Column(String(100), nullable=True)
    road_character = Column(String(100), nullable=True)
    road_type = Column(String(100), nullable=True)
    surface_type = Column(String(100), nullable=True)
    surface_condition = Column(String(100), nullable=True)
    road_condition = Column(String(100), nullable=True)
    weather = Column(String(100), nullable=True)
    road_markings = Column(String(100), nullable=True)
    spot_conditions = Column(Text, nullable=True)

    # Location identifiers
    road_junction = Column(String(200), nullable=True)
    accident_road = Column(String(300), nullable=True)
    landmark_first = Column(String(300), nullable=True)
    landmark_second = Column(String(300), nullable=True)
    description = Column(Text, nullable=True)

    # Coordinates (mandatory for map display)
    latitude = Column(Float, nullable=True, index=True)
    longitude = Column(Float, nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<AccidentData(id={self.id}, crime_no='{self.crime_no}', severity='{self.severity}', loc=({self.latitude},{self.longitude}))>"
