/**
 * NAVISCAPE Women Safety WS-2 — WhatsApp Emergency Alert Utility
 * Centralized utility for emergency message building, phone normalization,
 * wa.me URL generation, clipboard copying, and WhatsApp browser opening.
 */

/**
 * Normalize an Indian mobile number to digits-only international format: 91XXXXXXXXXX.
 * Accepts: 9739988032, +91 9739988032, +919739988032, 91 9739988032, 09739988032
 * Returns: '919739988032' (digits only, no '+' prefix, spaces, or dashes)
 */
export function normalizePhoneNumber(phoneNumber) {
  if (!phoneNumber) return null;
  const digits = String(phoneNumber).replace(/\D/g, '');

  if (digits.length === 12 && digits.startsWith('91') && /^[6-9]/.test(digits[2])) {
    return digits;
  }
  if (digits.length === 11 && digits.startsWith('0') && /^[6-9]/.test(digits[1])) {
    return `91${digits.slice(1)}`;
  }
  if (digits.length === 10 && /^[6-9]/.test(digits[0])) {
    return `91${digits}`;
  }
  if (digits.length >= 10) {
    return digits;
  }
  return null;
}

/**
 * Format timestamp for emergency message display
 */
export function formatEmergencyTime(dateInput) {
  if (!dateInput) {
    const d = new Date();
    const day = String(d.getDate()).padStart(2, '0');
    const month = d.toLocaleString('en-US', { month: 'short' });
    const year = d.getFullYear();
    const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    return `${day} ${month} ${year}, ${time}`;
  }
  try {
    const d = new Date(dateInput);
    if (isNaN(d.getTime())) return formatEmergencyTime(null);
    const day = String(d.getDate()).padStart(2, '0');
    const month = d.toLocaleString('en-US', { month: 'short' });
    const year = d.getFullYear();
    const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    return `${day} ${month} ${year}, ${time}`;
  } catch {
    return formatEmergencyTime(null);
  }
}

/**
 * Centralized Emergency Message Generator
 * Strictly uses captured real GPS coordinates.
 */
export function buildEmergencyWhatsAppMessage({ latitude, longitude, accuracy, triggeredAt }) {
  if (latitude == null || longitude == null || isNaN(latitude) || isNaN(longitude)) {
    throw new Error('Valid GPS coordinates are required for emergency message.');
  }

  const latFormatted = Number(latitude).toFixed(6);
  const lngFormatted = Number(longitude).toFixed(6);
  const mapsUrl = `https://www.google.com/maps?q=${latFormatted},${lngFormatted}`;

  const accuracyText = accuracy != null && !isNaN(accuracy)
    ? `📌 GPS Accuracy: ±${Math.round(accuracy)} m\n\n`
    : '';

  const timeText = formatEmergencyTime(triggeredAt);

  return `🚨 NAVISCAPE EMERGENCY ALERT

An emergency SOS has been activated.

📍 Current Location:
${mapsUrl}

${accuracyText}🕐 Time:
${timeText}

⚠️ Please contact me immediately.

— NAVISCAPE Emergency Safety System`;
}

/**
 * Generate official WhatsApp wa.me deep-link URL.
 */
export function buildWhatsAppUrl(phoneNumber, message) {
  const normalized = normalizePhoneNumber(phoneNumber);
  if (!normalized) return null;
  const encodedMessage = encodeURIComponent(message);
  return `https://wa.me/${normalized}?text=${encodedMessage}`;
}

/**
 * Opens WhatsApp deep-link in browser / mobile device.
 */
export function openWhatsAppAlert(phoneNumber, message) {
  const url = buildWhatsAppUrl(phoneNumber, message);
  if (!url) {
    return { success: false, reason: 'invalid_phone', url: null };
  }

  try {
    const win = window.open(url, '_blank', 'noopener,noreferrer');
    if (!win || win.closed || typeof win.closed === 'undefined') {
      return { success: false, reason: 'popup_blocked', url };
    }
    return { success: true, url };
  } catch {
    return { success: false, reason: 'popup_blocked', url };
  }
}

/**
 * Copy emergency message fallback.
 */
export async function copyEmergencyMessage(message) {
  if (!message) return false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(message);
      return true;
    }
  } catch {
    // fallback
  }

  try {
    const textarea = document.createElement('textarea');
    textarea.value = message;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const successful = document.execCommand('copy');
    document.body.removeChild(textarea);
    return successful;
  } catch {
    return false;
  }
}
