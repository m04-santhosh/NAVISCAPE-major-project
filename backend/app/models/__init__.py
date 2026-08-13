"""
Models package — registers all ORM models with SQLAlchemy's mapper registry.

IMPORTANT: All models MUST be imported here so that SQLAlchemy can resolve
string-based relationship targets (e.g. relationship("RouteHistory")) regardless
of which individual model module is imported first by routers or middleware.

Failure to import a model here causes:
    sqlalchemy.exc.InvalidRequestError:
        expression 'RouteHistory' failed to locate a name ('RouteHistory')
"""

# Import order: base models first, then models that reference others via FK/relationship
from .user import User           # defines relationship("RouteHistory")
from .traffic import TrafficData, RouteHistory  # RouteHistory must be imported for User.route_history to resolve
from .otp import OTPRecord
from .accident import AccidentData
from .road_hazard import RoadHazard

__all__ = [
    "User",
    "TrafficData",
    "RouteHistory",
    "OTPRecord",
    "AccidentData",
    "RoadHazard",
]
