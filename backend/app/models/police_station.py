from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from ..database import Base


class PoliceStation(Base):
    """
    SQLAlchemy model for Karnataka Police Stations.
    Source: KGIS (Karnataka Geographic Information System) KML Dataset.
    """
    __tablename__ = "police_stations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    object_id = Column(Integer, unique=True, index=True, nullable=False)
    department_code = Column(String(50), unique=True, index=True, nullable=False)
    station_name = Column(String(255), index=True, nullable=False)
    kgis_pol_sta_id = Column(Integer, nullable=True)
    kgis_code = Column(String(100), nullable=True)
    kgis_ps_code = Column(String(50), nullable=True)
    kgis_village_id = Column(Float, nullable=True)
    latitude = Column(Float, index=True, nullable=False)
    longitude = Column(Float, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_police_stations_lat_lng", "latitude", "longitude"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "object_id": self.object_id,
            "department_code": self.department_code,
            "station_name": self.station_name,
            "kgis_pol_sta_id": self.kgis_pol_sta_id,
            "kgis_code": self.kgis_code,
            "kgis_ps_code": self.kgis_ps_code,
            "kgis_village_id": self.kgis_village_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
