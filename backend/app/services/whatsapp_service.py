"""
NAVISCAPE Women Safety — WS-3A WhatsApp Emergency Message Service

Read-only helper service for generating emergency WhatsApp messages
and click-to-chat URLs. This service:

- Does NOT send any messages automatically.
- Does NOT integrate with Meta WhatsApp Cloud API or any external API.
- Does NOT make any outbound HTTP requests.
- Only generates message text and wa.me URLs for manual user action.

All coordinates MUST come from authenticated EmergencyEvent records.
"""

from urllib.parse import quote


def normalize_whatsapp_number(number: str) -> str:
    """
    Normalize an Indian mobile number to the international format required
    by wa.me URLs: 91XXXXXXXXXX (country code + 10 digits, no '+' prefix).

    Accepts formats: 9876543210, +919876543210, 09876543210
    Returns: 919876543210
    """
    if not number:
        raise ValueError("WhatsApp number cannot be empty.")

    import re
    cleaned = re.sub(r"[\s\-]", "", str(number).strip())

    # Remove +91 or 0 prefix to get 10-digit number
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]

    if len(cleaned) != 10 or not cleaned[0] in "6789":
        raise ValueError(f"Invalid Indian mobile number for WhatsApp: {number}")

    # wa.me format: country code + number, no '+'
    return f"91{cleaned}"


def generate_emergency_message(
    user_name: str,
    latitude: float,
    longitude: float,
    triggered_at: str,
) -> str:
    """
    Generate the emergency alert message containing:
    - User name
    - Google Maps URL from real EmergencyEvent GPS coordinates
    - Trigger timestamp

    The latitude/longitude MUST come from the authenticated EmergencyEvent.
    Never use preset, destination, police station, hospital, or fake coordinates.
    """
    maps_url = f"https://www.google.com/maps?q={latitude},{longitude}"

    message = (
        f"🚨 NAVISCAPE EMERGENCY ALERT\n"
        f"\n"
        f"{user_name} has activated an emergency alert.\n"
        f"\n"
        f"📍 Current location:\n"
        f"{maps_url}\n"
        f"\n"
        f"🕐 Time:\n"
        f"{triggered_at}\n"
        f"\n"
        f"Please contact them immediately."
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
