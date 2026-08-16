"""
NAVISCAPE Hospital Module — Hospital Model
SQLAlchemy model for Verified Karnataka Hospitals (hospital_facilities table).
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Index, Text
from ..database import Base


class Hospital(Base):
    """
    SQLAlchemy model for Verified Hospital Database.
    Source: Verified Karnataka Hospital Dataset (backend/data/karnataka_hospitals_verified.csv).
    """
    __tablename__ = "hospital_facilities"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source_id = Column(Integer, unique=True, index=True, nullable=False)
    hospital_name = Column(String(255), index=True, nullable=False)
    latitude = Column(Float, index=True, nullable=True)
    longitude = Column(Float, index=True, nullable=True)
    address = Column(Text, nullable=True)
    district = Column(String(100), index=True, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=True)
    hospital_category = Column(String(100), index=True, nullable=True)
    hospital_care_type = Column(String(100), nullable=True)
    discipline = Column(String(100), nullable=True)
    telephone = Column(String(100), nullable=True)
    mobile_number = Column(String(100), nullable=True)
    emergency_number = Column(String(100), nullable=True)
    ambulance_phone = Column(String(100), nullable=True)
    bloodbank_phone = Column(String(100), nullable=True)
    emergency_services = Column(String(255), nullable=True)
    specialties = Column(Text, nullable=True)
    facilities = Column(Text, nullable=True)
    total_beds = Column(Integer, nullable=True)
    website = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_hospital_facilities_lat_lng", "latitude", "longitude"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "source_id": self.source_id,
            "hospital_name": self.hospital_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": self.address,
            "district": self.district,
            "city": self.city,
            "state": self.state,
            "pincode": self.pincode,
            "hospital_category": self.hospital_category,
            "hospital_care_type": self.hospital_care_type,
            "discipline": self.discipline,
            "telephone": self.telephone,
            "mobile_number": self.mobile_number,
            "emergency_number": self.emergency_number,
            "ambulance_phone": self.ambulance_phone,
            "bloodbank_phone": self.bloodbank_phone,
            "emergency_services": self.emergency_services,
            "specialties": self.specialties,
            "facilities": self.facilities,
            "total_beds": self.total_beds,
            "website": self.website,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
