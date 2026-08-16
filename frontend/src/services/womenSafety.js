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
   * WS-2: Trigger Emergency SOS event with validated GPS coordinates
   * @param {Object} payload { latitude, longitude, location_accuracy_m }
   */
  async triggerSOS(payload) {
    const res = await api.post('/women-safety/emergency-events', payload);
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
};

export default womenSafetyService;
