"""
NAVISCAPE Email Service Bridge
Exports email_service and send_otp_email from app.services.email_service.
"""

from .services.email_service import EmailService, email_service, send_otp_email

__all__ = ["EmailService", "email_service", "send_otp_email"]
