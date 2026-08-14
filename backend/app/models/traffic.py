"""
Traffic Data ORM Model
Stores historical and real-time traffic measurements at junctions.
"""

from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, func, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from ..database import Base


class TrafficData(Base):
    __tablename__ = "traffic_data"
    __table_args__ = (
        UniqueConstraint("junction_id", "timestamp", name="uq_traffic_junction_timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    junction_id = Column(Integer, nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    vehicle_count = Column(Integer, nullable=False)
    avg_speed = Column(Float, nullable=True)
    congestion_level = Column(String(20), nullable=True)  # low, medium, high, critical
    day_of_week = Column(Integer, nullable=True)  # 0=Monday, 6=Sunday
    hour_of_day = Column(Integer, nullable=True)  # 0-23
    is_test = Column(Boolean, default=False, nullable=True)
    free_flow_speed = Column(Float, nullable=True)
    speed_ratio = Column(Float, nullable=True)

    def __repr__(self):
        return f"<TrafficData(junction={self.junction_id}, time={self.timestamp}, vehicles={self.vehicle_count})>"


class RouteHistory(Base):
    __tablename__ = "route_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_lat = Column(Float, nullable=False)
    source_lng = Column(Float, nullable=False)
    dest_lat = Column(Float, nullable=False)
    dest_lng = Column(Float, nullable=False)
    source_name = Column(String(200), nullable=True)
    dest_name = Column(String(200), nullable=True)
    distance_km = Column(Float, nullable=True)
    duration_min = Column(Float, nullable=True)
    safety_score = Column(Float, nullable=True)
    route_type = Column(String(20), nullable=True)  # shortest, safest, balanced
    created_at = Column(DateTime, server_default=func.now())

    # Relationship
    user = relationship("User", back_populates="route_history")

    def __repr__(self):
        return f"<RouteHistory(user={self.user_id}, type='{self.route_type}')>"


class TrafficHourly(Base):
    __tablename__ = "traffic_hourly"
    __table_args__ = (
        UniqueConstraint("junction_id", "timestamp", "is_test", name="uq_traffic_hourly_junction_time_test"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    junction_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    avg_speed = Column(Float, nullable=True)
    speed_ratio = Column(Float, nullable=True)
    avg_confidence = Column(Float, nullable=True)
    sample_count = Column(Integer, nullable=False, default=0)
    data_quality = Column(String(20), nullable=False)  # COMPLETE, PARTIAL, LOW_COVERAGE
    is_test = Column(Boolean, default=False, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<TrafficHourly(junction={self.junction_id}, time={self.timestamp}, quality={self.data_quality}, samples={self.sample_count})>"
