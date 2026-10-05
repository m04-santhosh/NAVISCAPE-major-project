import api from './api';

/**
 * Women Safety API Service — Emergency Profile, Trusted Contacts & SOS Events
 */

export const womenSafetyService = {
  /**
   * Get authenticated user's emergency profile and trusted contacts overview
   */
  async getOverview() {
    const res = await api.get('/women-safety/emergency-profile');
    return res.data;
  },

  /**
   * Update or create emergency profile and location-sharing consent
   * @param {Object} payload { emergency_mobile, emergency_email, location_sharing_consent }
   */
  async updateProfile(payload) {
    const res = await api.put('/women-safety/emergency-profile', payload);
    return res.data;
  },

  /**
   * Add one trusted contact (max 4 allowed)
   * @param {Object} payload { contact_name, relationship, mobile_number, email }
   */
  async addContact(payload) {
    const res = await api.post('/women-safety/trusted-contacts', payload);
    return res.data;
  },

  /**
   * Update an existing trusted contact
   * @param {number} contactId
   * @param {Object} payload { contact_name, relationship, mobile_number, email }
   */
  async updateContact(contactId, payload) {
    const res = await api.put(`/women-safety/trusted-contacts/${contactId}`, payload);
    return res.data;
  },

  /**
   * Delete a trusted contact
   * @param {number} contactId
   */
  async deleteContact(contactId) {
    const res = await api.delete(`/women-safety/trusted-contacts/${contactId}`);
    return res.data;
  },

  /**
   * WS-2: Get authenticated user's current ACTIVE emergency event
   */
  async getActiveEmergencyEvent() {
    const res = await api.get('/women-safety/emergency-events/active');
    return res.data;
  },

  /**
   * WS-1: Trigger Emergency SOS event with validated real GPS coordinates
   * @param {Object} payload { latitude, longitude, accuracy_m }
   */
  async triggerEmergency(payload) {
    const res = await api.post('/women-safety/emergency', payload);
    return res.data;
  },

  /**
   * WS-2: Trigger Emergency SOS event with validated GPS coordinates
   * @param {Object} payload { latitude, longitude, location_accuracy_m }
   */
  async triggerSOS(payload) {
    const res = await api.post('/women-safety/emergency', {
      latitude: payload.latitude,
      longitude: payload.longitude,
      accuracy_m: payload.accuracy_m ?? payload.location_accuracy_m ?? null,
    });
    return res.data;
  },

  /**
   * WS-2: Cancel an active emergency event
   * @param {number} eventId
   */
  async cancelEmergencyEvent(eventId) {
    const res = await api.post(`/women-safety/emergency-events/${eventId}/cancel`);
    return res.data;
  },

  /**
   * WS-3A: Get WhatsApp alert URLs for an active emergency event
   * Returns per-contact WhatsApp click-to-chat URLs generated from real EmergencyEvent GPS.
   * Does NOT send any messages — user must manually press Send in WhatsApp.
   * @param {number} eventId
   */
  async getWhatsAppAlerts(eventId) {
    const res = await api.get(`/women-safety/emergency-events/${eventId}/whatsapp-alerts`);
    return res.data;
  },

  /**
   * WS-3: Record an emergency action audit trail entry
   * @param {number} eventId
   * @param {Object} payload { action_type, contact_type, contact_name, contact_phone, latitude, longitude, metadata }
   */
  async recordAction(eventId, payload) {
    const res = await api.post(`/women-safety/emergency/${eventId}/actions`, payload);
    return res.data;
  },

  /**
   * WS-3: Get chronological emergency actions timeline
   * @param {number} eventId
   */
  async getTimeline(eventId) {
    const res = await api.get(`/women-safety/emergency/${eventId}/timeline`);
    return res.data;
  },

  /**
   * WS-3: Update emergency event status (ACTIVE, ALERTS_PREPARED, CONTACTS_NOTIFIED, CANCELLED, RESOLVED)
   * @param {number} eventId
   * @param {string} newStatus
   */
  async updateStatus(eventId, newStatus) {
    const res = await api.patch(`/women-safety/emergency/${eventId}/status`, { status: newStatus });
    return res.data;
  },

  /**
   * WS-3: Mark emergency event as resolved
   * @param {number} eventId
   */
  async resolveEmergencyEvent(eventId) {
    const res = await api.post(`/women-safety/emergency/${eventId}/actions`, {
      action_type: 'EMERGENCY_RESOLVED',
    });
    return res.data;
  },
};

export default womenSafetyService;
