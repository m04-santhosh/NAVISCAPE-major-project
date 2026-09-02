"""
NAVISCAPE - SMTP Gmail Connectivity & Verification Script
Safely tests SMTP configuration, TLS connection, authentication, and test email sending.
NEVER prints or exposes SMTP passwords or sensitive secrets.
"""

import os
import sys
from dotenv import load_dotenv

# Reconfigure stdout/stderr for UTF-8 compatibility on Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Ensure backend root is in python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Load .env file
load_dotenv(os.path.join(backend_dir, ".env"))
load_dotenv()

from app.config import settings
from app.email_service import email_service


def run_smtp_verification(test_recipient: str = None):
    print("=" * 60)
    print("  NAVISCAPE Gmail SMTP Verification")
    print("=" * 60)

    # 1. Verify Configuration
    print("\n[1/3] Checking SMTP Configuration...")
    if not settings.SMTP_HOST:
        print("  [-] SMTP_HOST is not set in environment.")
        return False
    if not settings.SMTP_USERNAME:
        print("  [-] SMTP_USERNAME is not set in environment.")
        return False
    if not settings.SMTP_PASSWORD:
        print("  [-] SMTP_PASSWORD is not set in environment.")
        return False

    print("  [OK] SMTP configuration found:")
    print(f"       - Host: {settings.SMTP_HOST}")
    print(f"       - Port: {settings.SMTP_PORT}")
    print(f"       - Username: {settings.SMTP_USERNAME}")
    print(f"       - From Name: {settings.SMTP_FROM_NAME}")
    print(f"       - From Email: {settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME}")
    print("       - Password: [CONFIGURED - HIDDEN FOR SECURITY]")

    # 2. Test Connection & Authentication
    print("\n[2/3] Connecting and Authenticating with Gmail SMTP...")
    auth_result = email_service.verify_connection()
    if not auth_result.get("success"):
        print(f"  [-] SMTP Authentication failed: {auth_result.get('message')}")
        return False

    print("  [OK] SMTP authentication successful!")

    # 3. Send Test Email (to recipient or self)
    recipient = test_recipient or settings.SMTP_USERNAME
    print(f"\n[3/3] Sending test verification email to: {recipient}...")
    
    send_result = email_service.send_email(
        to_email=recipient,
        subject="[NAVISCAPE] SMTP Test Verification",
        body_text=(
            "Hello from NAVISCAPE!\n\n"
            "This test email confirms that your Gmail SMTP integration is working correctly.\n"
            "Backend server is ready to send OTP codes, security alerts, and transactional messages.\n\n"
            "— NAVISCAPE Team"
        ),
        body_html="""<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px;">
  <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155;">
    <h2 style="color: #38bdf8; margin-top: 0;">NAVISCAPE SMTP Test</h2>
    <p>Your Gmail SMTP configuration is fully working and verified!</p>
    <div style="background-color: #090d16; padding: 12px; border-radius: 8px; font-family: monospace; color: #4ade80;">
      ✓ STARTTLS Connection: OK<br>
      ✓ Gmail Authentication: OK<br>
      ✓ Email Delivery: OK
    </div>
    <p style="font-size: 12px; color: #94a3b8; margin-top: 20px;">NAVISCAPE Major Project 2026</p>
  </div>
</body>
</html>"""
    )

    if not send_result.get("success"):
        print(f"  [-] Failed to send test email: {send_result.get('message')}")
        return False

    print("  [OK] Test email sent successfully!")
    print("\n" + "=" * 60)
    print("  All SMTP checks passed successfully.")
    print("=" * 60 + "\n")
    return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    success = run_smtp_verification(target)
    sys.exit(0 if success else 1)
