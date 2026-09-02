"""
NAVISCAPE Services Package
"""

from ..email_service import email_service, otp_store, EmailService, OTPStore

__all__ = [
    "email_service",
    "otp_store",
    "EmailService",
    "OTPStore",
]
