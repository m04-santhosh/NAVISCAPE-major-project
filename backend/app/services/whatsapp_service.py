"""
NAVISCAPE Women Safety — WS-2 WhatsApp Emergency Alert Message Service

Read-only helper service for generating emergency WhatsApp messages
and click-to-chat URLs. This service:

- Does NOT send any messages automatically.
- Does NOT integrate with Meta WhatsApp Cloud API or any external API.
- Does NOT make any outbound HTTP requests.
- Only generates message text and wa.me URLs for manual user action.

All coordinates MUST come from authenticated EmergencyEvent records.
"""

from urllib.parse import quote
import re


def normalize_whatsapp_number(number: str) -> str:
    """
    Normalize an Indian mobile number to international format required by wa.me URLs: 91XXXXXXXXXX.
    Accepts: 9739988032, +91 9739988032, +919739988032, 91 9739988032, 09739988032.
    Returns: 919739988032 (digits only, no '+' prefix, spaces, or dashes).
    """
    if not number:
        raise ValueError("WhatsApp number cannot be empty.")

    digits = re.sub(r"\D", "", str(number).strip())

    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits
    elif len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        return f"91{digits[1:]}"
    elif len(digits) == 10 and digits[0] in "6789":
        return f"91{digits}"
    elif len(digits) >= 10:
        return digits
    else:
        raise ValueError(f"Invalid phone number for WhatsApp: {number}")


def generate_emergency_message(
    user_name: str = "NAVISCAPE User",
    latitude: float = 0.0,
    longitude: float = 0.0,
    accuracy_m: float | None = None,
    triggered_at: str | None = None,
) -> str:
    """
    Generate the emergency alert message containing:
    - SOS alert notice
    - Google Maps URL from real EmergencyEvent GPS coordinates
    - Accuracy indicator (if available)
    - Trigger timestamp
    - Contact request

    The latitude/longitude MUST come from the authenticated EmergencyEvent.
    Never use preset, destination, police station, hospital, or fake coordinates.
    """
    maps_url = f"https://www.google.com/maps?q={latitude},{longitude}"

    accuracy_str = f"\n📌 GPS Accuracy: ±{round(accuracy_m)} m\n" if accuracy_m is not None else ""
    time_str = f"\n🕐 Time:\n{triggered_at}\n" if triggered_at else ""

    message = (
        f"🚨 NAVISCAPE EMERGENCY ALERT\n"
        f"\n"
        f"An emergency SOS has been activated.\n"
        f"\n"
        f"📍 Current Location:\n"
        f"{maps_url}\n"
        f"{accuracy_str}"
        f"{time_str}"
        f"\n"
        f"⚠️ Please contact me immediately.\n"
        f"\n"
        f"— NAVISCAPE Emergency Safety System"
    )
    return message


def generate_whatsapp_url(whatsapp_number: str, message: str) -> str:
    """
    Generate a WhatsApp click-to-chat URL.

    Returns: https://wa.me/91XXXXXXXXXX?text=<URL_ENCODED_MESSAGE>

    This URL, when opened, pre-fills the message in WhatsApp.
    The user MUST manually press Send — this does NOT deliver the message.
    """
    normalized = normalize_whatsapp_number(whatsapp_number)
    encoded_message = quote(message, safe="")
    return f"https://wa.me/{normalized}?text={encoded_message}"
