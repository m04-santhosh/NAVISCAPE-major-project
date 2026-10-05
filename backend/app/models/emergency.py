"""
NAVISCAPE Women Safety — Emergency Event ORM Model
Re-exports the existing EmergencyEvent model for modular schema & router access.
"""

from .emergency_event import EmergencyEvent

__all__ = ["EmergencyEvent"]
