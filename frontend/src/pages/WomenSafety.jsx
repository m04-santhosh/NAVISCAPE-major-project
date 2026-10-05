import { useState, useEffect, useCallback, useRef } from 'react';
import toast from 'react-hot-toast';
import {
  HiShieldCheck,
  HiUserGroup,
  HiPhone,
  HiMail,
  HiPlus,
  HiPencil,
  HiTrash,
  HiCheckCircle,
  HiExclamationCircle,
  HiXCircle,
  HiInformationCircle,
  HiStop,
} from 'react-icons/hi';
import womenSafetyService from '../services/womenSafety';
import {
  buildEmergencyWhatsAppMessage,
  openWhatsAppAlert,
  copyEmergencyMessage,
  normalizePhoneNumber,
} from '../utils/emergencyMessage';

function formatActivationTime(dateInput) {
  if (!dateInput) return 'Just now';
  try {
    const d = new Date(dateInput);
    if (isNaN(d.getTime())) return 'Just now';
    const day = String(d.getDate()).padStart(2, '0');
    const month = d.toLocaleString('en-US', { month: 'short' });
    const year = d.getFullYear();
    const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    return `${day} ${month} ${year}, ${time}`;
  } catch {
    return 'Just now';
  }
}

export default function WomenSafety() {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState(null);

  // Active Emergency State (WS-1)
  const [activeEmergency, setActiveEmergency] = useState(null);
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);
  const [cancellingEmergency, setCancellingEmergency] = useState(false);

  // SOS Trigger & Loading Phase States (WS-1)
  const [sosPhaseText, setSosPhaseText] = useState('');

  // SOS 3-Second Hold State (WS-2)
  const [holdProgress, setHoldProgress] = useState(0); // 0 to 100
  const [isHolding, setIsHolding] = useState(false);
  const [isConfirmSosModalOpen, setIsConfirmSosModalOpen] = useState(false);
  const [activatingSos, setActivatingSos] = useState(false);
  const holdTimerRef = useRef(null);
  const holdStartTimeRef = useRef(null);

  // Profile Form State (WS-1)
  const [emergencyMobile, setEmergencyMobile] = useState('');
  const [emergencyEmail, setEmergencyEmail] = useState('');
  const [consent, setConsent] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  // Contact Modal / Form State (WS-1)
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingContactId, setEditingContactId] = useState(null);
  const [contactName, setContactName] = useState('');
  const [relationship, setRelationship] = useState('');
  const [contactMobile, setContactMobile] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactWhatsApp, setContactWhatsApp] = useState('');
  const [contactWhatsAppConsent, setContactWhatsAppConsent] = useState(false);
  const [savingContact, setSavingContact] = useState(false);

  // Delete Confirmation State (WS-1)
  const [contactToDelete, setContactToDelete] = useState(null);
  const [deletingContact, setDeletingContact] = useState(false);

  // WS-3: Live Emergency Timeline & Action Tracking
  const [timeline, setTimeline] = useState([]);
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [isResolveModalOpen, setIsResolveModalOpen] = useState(false);
  const [resolvingEmergency, setResolvingEmergency] = useState(false);

  const fetchOverview = useCallback(async (showLoader = true) => {
    if (showLoader) setLoading(true);
    try {
      const data = await womenSafetyService.getOverview();
      setOverview(data);
      if (data.emergency_profile) {
        setEmergencyMobile(data.emergency_profile.emergency_mobile || '');
        setEmergencyEmail(data.emergency_profile.emergency_email || '');
        setConsent(Boolean(data.emergency_profile.location_sharing_consent));
      }
      try {
        const activeRes = await womenSafetyService.getActiveEmergencyEvent();
        if (activeRes && activeRes.active && activeRes.emergency_event) {
          setActiveEmergency(activeRes.emergency_event);
        } else {
          setActiveEmergency(null);
        }
      } catch {
        setActiveEmergency(null);
      }
    } catch (err) {
      console.error('Failed to load emergency profile overview:', err);
      toast.error('Failed to load Women Safety profile overview.');
    } finally {
      if (showLoader) setLoading(false);
    }
  }, []);

  // Fetch timeline for active emergency session
  const fetchTimeline = useCallback(async (eventId) => {
    if (!eventId) {
      setTimeline([]);
      return;
    }
    setLoadingTimeline(true);
    try {
      const res = await womenSafetyService.getTimeline(eventId);
      if (res && res.timeline) {
        setTimeline(res.timeline);
        if (res.status) {
          setActiveEmergency((prev) => (prev ? { ...prev, status: res.status } : prev));
        }
      }
    } catch (err) {
      console.error('Failed to fetch emergency timeline:', err);
    } finally {
      setLoadingTimeline(false);
    }
  }, []);

  useEffect(() => {
    fetchOverview(true);
  }, [fetchOverview]);

  useEffect(() => {
    if (activeEmergency?.id) {
      fetchTimeline(activeEmergency.id);
    }
  }, [activeEmergency?.id, fetchTimeline]);

  // ── WS-2 & WS-3: Real Device WhatsApp Alert, Call & Action Handlers ──────

  const handleTriggerWhatsApp = async (phone, contactKey, contactName) => {
    if (!activeEmergency) return;

    if (!phone || !normalizePhoneNumber(phone)) {
      setWhatsappStatus((prev) => ({
        ...prev,
        [contactKey]: {
          status: 'error',
          message: 'WhatsApp unavailable — no valid mobile number configured.',
        },
      }));
      toast.error('WhatsApp unavailable — no valid mobile number configured.');
      return;
    }

    try {
      const message = buildEmergencyWhatsAppMessage({
        latitude: activeEmergency.latitude,
        longitude: activeEmergency.longitude,
        accuracy: activeEmergency.accuracy_m ?? activeEmergency.location_accuracy_m,
        triggeredAt: activeEmergency.triggered_at,
        contactName,
      });

      const res = openWhatsAppAlert(phone, message);

      if (res.success) {
        setWhatsappStatus((prev) => ({
          ...prev,
          [contactKey]: {
            status: 'opened',
            message: 'WhatsApp opened. Press Send inside WhatsApp to deliver.',
          },
        }));
        toast.success(`WhatsApp opened for ${contactName}. Tap Send in WhatsApp to deliver.`, { icon: '📱' });

        try {
          await womenSafetyService.recordAction(activeEmergency.id, {
            action_type: 'WHATSAPP_OPENED',
            contact_type: contactKey === 'primary' ? 'PRIMARY' : 'TRUSTED',
            contact_name: contactName,
            contact_phone: phone,
          });
          fetchTimeline(activeEmergency.id);
        } catch (e) {
          console.error('Failed to record WHATSAPP_OPENED action:', e);
        }
      } else {
        setWhatsappStatus((prev) => ({
          ...prev,
          [contactKey]: {
            status: 'error',
            message: 'WhatsApp could not be opened automatically. Please allow pop-ups or use the contact button again.',
          },
        }));
        toast.error('WhatsApp could not be opened automatically. Please allow pop-ups or try again.');
      }
    } catch (err) {
      console.error('Failed to trigger WhatsApp alert:', err);
      toast.error('Failed to prepare emergency WhatsApp message.');
    }
  };

  const handleConfirmAlertSent = async (contactName, contactKey, phone) => {
    if (!activeEmergency) return;
    try {
      await womenSafetyService.recordAction(activeEmergency.id, {
        action_type: 'ALERT_SENT_CONFIRMED',
        contact_type: contactKey === 'primary' ? 'PRIMARY' : 'TRUSTED',
        contact_name: contactName,
        contact_phone: phone,
      });

      setWhatsappStatus((prev) => ({
        ...prev,
        [contactKey]: {
          status: 'confirmed',
          message: 'Alert sent confirmed by user.',
        },
      }));

      toast.success(`Alert confirmed as sent to ${contactName}.`, { icon: '✓' });
      fetchTimeline(activeEmergency.id);
    } catch (err) {
      console.error('Failed to confirm alert sent:', err);
      toast.error('Failed to record alert confirmation.');
    }
  };

  const handleInitiateCall = async (phone, contactName, contactType) => {
    if (!activeEmergency) return;
    try {
      const actionType = contactType === 'POLICE' ? 'POLICE_CALLED' : 'EMERGENCY_CONTACT_CALLED';
      await womenSafetyService.recordAction(activeEmergency.id, {
        action_type: actionType,
        contact_type: contactType,
        contact_name: contactName,
        contact_phone: phone,
      });

      toast.success(`Emergency call to ${contactName} (${phone}) initiated. Confirm on your device.`, { icon: '📞' });
      fetchTimeline(activeEmergency.id);
    } catch (err) {
      console.error('Failed to record call action:', err);
    } finally {
      window.location.href = `tel:${phone}`;
    }
  };

  const handleCopyWhatsAppMessage = async (contactName, contactKey) => {
    if (!activeEmergency) return;
    try {
      const message = buildEmergencyWhatsAppMessage({
        latitude: activeEmergency.latitude,
        longitude: activeEmergency.longitude,
        accuracy: activeEmergency.accuracy_m ?? activeEmergency.location_accuracy_m,
        triggeredAt: activeEmergency.triggered_at,
        contactName,
      });

      const success = await copyEmergencyMessage(message);
      if (success) {
        setWhatsappStatus((prev) => ({
          ...prev,
          [contactKey]: {
            status: 'copied',
            message: 'Emergency message copied. Open WhatsApp and paste it into the emergency contact chat.',
          },
        }));
        toast.success('Emergency message copied. Paste it into WhatsApp.', { icon: '📋' });
      } else {
        toast.error('Failed to copy emergency message to clipboard.');
      }
    } catch {
      toast.error('Failed to copy emergency message.');
    }
  };

  const handleConfirmResolveEmergency = async () => {
    if (!activeEmergency) return;
    setResolvingEmergency(true);
    const toastId = toast.loading('Resolving emergency session...');
    try {
      await womenSafetyService.resolveEmergencyEvent(activeEmergency.id);
      setActiveEmergency(null);
      setTimeline([]);
      setWhatsappAlerts(null);
      setWhatsappStatus({});
      setIsResolveModalOpen(false);
      toast.success('Emergency session resolved.', { id: toastId, icon: '✅' });
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to resolve emergency session.';
      toast.error(msg, { id: toastId });
    } finally {
      setResolvingEmergency(false);
    }
  };

  // ── WS-1: Profile Save ─────────────────────────────────────────────────────

  const handleSaveProfile = async (e) => {
    e.preventDefault();

    const cleanedMobile = emergencyMobile.trim().replace(/[\s-]/g, '');
    if (cleanedMobile && !/^(?:\+91|0)?[6-9]\d{9}$/.test(cleanedMobile)) {
      toast.error('Please enter a valid 10-digit Indian mobile number.');
      return;
    }

    if (emergencyEmail.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emergencyEmail.trim())) {
      toast.error('Please enter a valid email address.');
      return;
    }

    setSavingProfile(true);
    try {
      const updated = await womenSafetyService.updateProfile({
        emergency_mobile: cleanedMobile || null,
        emergency_email: emergencyEmail.trim() || null,
        location_sharing_consent: consent,
      });
      setOverview(updated);
      toast.success('Emergency profile saved successfully.', { icon: '🛡️' });
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to save emergency profile.';
      toast.error(msg);
    } finally {
      setSavingProfile(false);
    }
  };

  // ── WS-1: Contact Form Submit ──────────────────────────────────────────────

  const handleOpenAddModal = () => {
    if (overview && overview.contacts_count >= 4) {
      toast.error('You can add up to 4 trusted contacts.');
      return;
    }
    setEditingContactId(null);
    setContactName('');
    setRelationship('');
    setContactMobile('');
    setContactEmail('');
    setContactWhatsApp('');
    setContactWhatsAppConsent(false);
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (contact) => {
    setEditingContactId(contact.id);
    setContactName(contact.contact_name);
    setRelationship(contact.relationship);
    setContactMobile(contact.mobile_number);
    setContactEmail(contact.email || '');
    setContactWhatsApp(contact.whatsapp_number || '');
    setContactWhatsAppConsent(Boolean(contact.whatsapp_alert_consent));
    setIsModalOpen(true);
  };

  const handleSaveContact = async (e) => {
    e.preventDefault();

    if (!contactName.trim()) {
      toast.error('Contact name is required.');
      return;
    }
    if (!relationship.trim()) {
      toast.error('Relationship is required.');
      return;
    }

    const cleanedMobile = contactMobile.trim().replace(/[\s-]/g, '');
    if (!/^(?:\+91|0)?[6-9]\d{9}$/.test(cleanedMobile)) {
      toast.error('Please enter a valid 10-digit Indian mobile number for this contact.');
      return;
    }

    if (contactEmail.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contactEmail.trim())) {
      toast.error('Please enter a valid email address or leave it blank.');
      return;
    }

    // WS-3A: Validate WhatsApp number if provided
    const cleanedWhatsApp = contactWhatsApp.trim().replace(/[\s-]/g, '');
    if (cleanedWhatsApp && !/^(?:\+91|0)?[6-9]\d{9}$/.test(cleanedWhatsApp)) {
      toast.error('Please enter a valid 10-digit Indian mobile number for WhatsApp.');
      return;
    }

    setSavingContact(true);
    try {
      const payload = {
        contact_name: contactName.trim(),
        relationship: relationship.trim(),
        mobile_number: cleanedMobile,
        email: contactEmail.trim() || null,
        whatsapp_number: cleanedWhatsApp || null,
        whatsapp_alert_consent: contactWhatsAppConsent,
      };

      if (editingContactId) {
        await womenSafetyService.updateContact(editingContactId, payload);
        toast.success('Trusted contact updated successfully.');
      } else {
        await womenSafetyService.addContact(payload);
        toast.success('Trusted contact added successfully.');
      }

      setIsModalOpen(false);
      await fetchOverview(false);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to save trusted contact.';
      toast.error(msg);
    } finally {
      setSavingContact(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!contactToDelete) return;
    setDeletingContact(true);
    try {
      await womenSafetyService.deleteContact(contactToDelete.id);
      toast.success('Trusted contact removed successfully.');
      setContactToDelete(null);
      await fetchOverview(false);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to delete contact.';
      toast.error(msg);
    } finally {
      setDeletingContact(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen p-6 lg:p-10 flex flex-col items-center justify-center space-y-4">
        <div className="w-12 h-12 border-4 border-rose-500/30 border-t-rose-500 rounded-full animate-spin" />
        <p className="text-sm font-semibold text-surface-400">Loading Women Safety Protection Profile...</p>
      </div>
    );
  }

  const contacts = overview?.trusted_contacts || [];
  const hasMobile = Boolean(overview?.has_emergency_mobile);
  const hasConsent = Boolean(overview?.location_sharing_consent);

  // Compute Hold Countdown Display
  const remainingSeconds = Math.max(1, Math.ceil((3000 - (holdProgress / 100) * 3000) / 1000));

  return (
    <div className="min-h-screen p-4 sm:p-6 lg:p-8 space-y-8 max-w-7xl mx-auto overflow-y-auto">
      {/* ── HEADER & DISCLAIMER ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-surface-800/80 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-pink-500/10 border border-pink-500/30 text-pink-400 flex items-center justify-center text-xl shadow-lg">
              <HiShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tight text-surface-100 flex items-center gap-2">
                WOMEN SAFETY
                <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-pink-500/20 text-pink-300 border border-pink-500/30">
                  WS-1 Emergency Protection
                </span>
              </h1>
              <p className="text-xs text-surface-400 font-medium">Emergency Protection Profile, Trusted Contacts & Authenticated Real GPS SOS</p>
            </div>
          </div>
        </div>

        {/* Global Readiness Badge */}
        <div className="flex items-center gap-3">
          <div
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold border transition-all ${
              activeEmergency
                ? 'bg-rose-950/80 border-rose-500/60 text-rose-300 shadow-rose-950/50 shadow-lg animate-pulse'
                : isProfileComplete
                ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-300 shadow-emerald-950/40 shadow-lg'
                : 'bg-amber-950/40 border-amber-500/40 text-amber-300'
            }`}
          >
            {activeEmergency ? (
              <>
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping" />
                <span>EMERGENCY: ACTIVE</span>
              </>
            ) : isProfileComplete ? (
              <>
                <HiCheckCircle className="w-5 h-5 text-emerald-400" />
                <span>Profile Status: READY</span>
              </>
            ) : (
              <>
                <HiExclamationCircle className="w-5 h-5 text-amber-400" />
                <span>Profile Status: INCOMPLETE</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Notice Banner */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-surface-900/90 border border-surface-800 text-surface-300 text-xs leading-relaxed">
        <HiInformationCircle className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-surface-200">Security & Privacy Assurance:</span> Your emergency contact
          information is encrypted and used strictly for authorized emergency-response workflows. NAVISCAPE captures
          real GPS coordinates only upon explicit SOS trigger and confirmation.
        </div>
      </div>

      {/* ── WS-1: ACTIVE EMERGENCY BANNER OR SOS TRIGGER CARD ──────────────── */}
      {activeEmergency ? (
        <div className="p-6 rounded-2xl bg-gradient-to-r from-rose-950/95 via-red-950/80 to-surface-900 border-2 border-rose-500 shadow-2xl shadow-rose-950/60 space-y-5 animate-fadeIn">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-2xl bg-rose-500/20 border border-rose-500/50 text-rose-400 flex items-center justify-center flex-shrink-0 shadow-lg text-2xl relative">
                <span className="w-4 h-4 rounded-full bg-rose-500 animate-ping absolute" />
                <span className="relative">🔴</span>
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-black tracking-tight text-white flex items-center gap-2">
                    🔴 EMERGENCY ACTIVE
                  </h2>
                  <span className="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-rose-500 text-white uppercase tracking-wider shadow-sm">
                    {activeEmergency.status || 'ACTIVE'}
                  </span>
                </div>
                <p className="text-xs text-rose-200 font-semibold">
                  Emergency session activated successfully.
                </p>
                <div className="flex flex-wrap items-center gap-3 pt-1 text-xs">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 font-bold">
                    <span>📍</span> Current location captured ✓
                  </span>
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 font-bold">
                    <span>✓</span> Emergency event registered
                  </span>
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 font-bold">
                    <span>💬</span> Alert message prepared ✓
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2.5 flex-wrap sm:flex-nowrap">
              {/* WS-1 Step 8: View Current Location Google Maps Link */}
              {activeEmergency.latitude != null && activeEmergency.longitude != null && (
                <a
                  href={`https://www.google.com/maps?q=${activeEmergency.latitude},${activeEmergency.longitude}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 active:scale-98 text-white text-xs font-bold transition-all shadow-lg shadow-cyan-950/40 cursor-pointer flex-shrink-0"
                  id="view-current-location-btn"
                >
                  <span>📍</span>
                  <span>View Current Location</span>
                </a>
              )}

              <button
                onClick={() => setIsResolveModalOpen(true)}
                className="btn-primary !bg-emerald-600 hover:!bg-emerald-500 text-xs !py-2.5 !px-5 font-bold flex items-center justify-center gap-2 shadow-lg shadow-emerald-950/40 flex-shrink-0 cursor-pointer"
                id="resolve-emergency-btn"
              >
                <span>✅</span>
                <span>RESOLVE EMERGENCY</span>
              </button>

              <button
                onClick={() => setIsCancelModalOpen(true)}
                className="btn-primary !bg-rose-700 hover:!bg-rose-600 text-xs !py-2.5 !px-5 font-bold flex items-center justify-center gap-2 shadow-lg shadow-rose-900/40 flex-shrink-0 cursor-pointer"
              >
                <HiStop className="w-4 h-4" />
                <span>CANCEL EMERGENCY</span>
              </button>
            </div>
          </div>

          {/* Quick Emergency Actions Bar (WS-3 Requirement 7) */}
          <div className="p-4 rounded-xl bg-surface-950/90 border border-surface-800 space-y-2">
            <span className="text-[10px] font-bold text-surface-400 uppercase tracking-wider block">
              QUICK EMERGENCY ACTIONS
            </span>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <button
                onClick={() => {
                  const phone = overview?.emergency_profile?.emergency_mobile || contacts[0]?.mobile_number;
                  const name = overview?.emergency_profile?.emergency_mobile ? 'Primary Contact' : (contacts[0]?.contact_name || 'Emergency Contact');
                  if (phone) {
                    handleInitiateCall(phone, name, 'PRIMARY');
                  } else {
                    toast.error('No emergency contact mobile number configured.');
                  }
                }}
                className="flex items-center justify-center gap-2 p-3 rounded-xl bg-rose-950/70 hover:bg-rose-900/80 border border-rose-500/40 text-rose-200 text-xs font-bold transition-all active:scale-98 cursor-pointer shadow-md"
                id="quick-call-contact-btn"
              >
                <span>📞</span>
                <span className="truncate">CALL CONTACT</span>
              </button>

              <button
                onClick={() => handleInitiateCall('112', 'National Emergency Police', 'POLICE')}
                className="flex items-center justify-center gap-2 p-3 rounded-xl bg-red-950/80 hover:bg-red-900 border border-red-500/60 text-white text-xs font-black transition-all active:scale-98 cursor-pointer shadow-md"
                id="quick-call-112-btn"
              >
                <span>🚨</span>
                <span className="truncate">CALL 112</span>
              </button>

              {activeEmergency.latitude != null && activeEmergency.longitude != null ? (
                <a
                  href={`https://www.google.com/maps?q=${activeEmergency.latitude},${activeEmergency.longitude}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 p-3 rounded-xl bg-cyan-950/70 hover:bg-cyan-900/80 border border-cyan-500/40 text-cyan-200 text-xs font-bold transition-all active:scale-98 cursor-pointer shadow-md text-center"
                >
                  <span>📍</span>
                  <span className="truncate">VIEW LOCATION</span>
                </a>
              ) : (
                <button
                  disabled
                  className="flex items-center justify-center gap-2 p-3 rounded-xl bg-surface-900 text-surface-500 border border-surface-800 text-xs font-bold cursor-not-allowed opacity-50"
                >
                  <span>📍</span>
                  <span className="truncate">VIEW LOCATION</span>
                </button>
              )}

              <button
                onClick={() => {
                  const phone = overview?.emergency_profile?.emergency_mobile || contacts[0]?.whatsapp_number || contacts[0]?.mobile_number;
                  const key = overview?.emergency_profile?.emergency_mobile ? 'primary' : `contact_${contacts[0]?.id}`;
                  const name = overview?.emergency_profile?.emergency_mobile ? 'Primary Contact' : contacts[0]?.contact_name;
                  if (phone) {
                    handleTriggerWhatsApp(phone, key, name);
                  } else {
                    toast.error('No valid WhatsApp mobile number configured.');
                  }
                }}
                className="flex items-center justify-center gap-2 p-3 rounded-xl bg-emerald-950/70 hover:bg-emerald-900/80 border border-emerald-500/40 text-emerald-200 text-xs font-bold transition-all active:scale-98 cursor-pointer shadow-md"
                id="quick-open-whatsapp-btn"
              >
                <span>💬</span>
                <span className="truncate">OPEN WHATSAPP</span>
              </button>
            </div>
          </div>

          {/* Emergency Details Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-rose-500/30 text-xs">
            <div className="p-3.5 rounded-xl bg-surface-950/70 border border-rose-500/30">
              <span className="text-[10px] font-bold text-surface-400 uppercase tracking-wider block">Current Location</span>
              <p className="font-mono font-bold text-rose-300 mt-1 text-sm">
                {Number(activeEmergency.latitude).toFixed(6)}, {Number(activeEmergency.longitude).toFixed(6)}
              </p>
            </div>
            <div className="p-3.5 rounded-xl bg-surface-950/70 border border-rose-500/30">
              <span className="text-[10px] font-bold text-surface-400 uppercase tracking-wider block">Accuracy</span>
              <p className="font-mono font-bold text-surface-200 mt-1 text-sm">
                {(activeEmergency.accuracy_m ?? activeEmergency.location_accuracy_m) != null
                  ? `±${Math.round(activeEmergency.accuracy_m ?? activeEmergency.location_accuracy_m)} m`
                  : 'Standard GPS'}
              </p>
            </div>
            <div className="p-3.5 rounded-xl bg-surface-950/70 border border-rose-500/30">
              <span className="text-[10px] font-bold text-surface-400 uppercase tracking-wider block">Activated</span>
              <p className="font-bold text-surface-200 mt-1 text-sm">
                {formatActivationTime(activeEmergency.triggered_at)}
              </p>
            </div>
          </div>

          {/* ── WS-2 & WS-3: EMERGENCY CONTACTS & WHATSAPP ALERTS SECTION ──────────────── */}
          <div className="p-5 rounded-2xl bg-surface-950/80 border border-emerald-500/40 space-y-4 pt-4 border-t">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-surface-800 pb-3">
              <div className="flex items-center gap-2.5">
                <span className="text-xl">💬</span>
                <div>
                  <h3 className="text-sm font-black text-white uppercase tracking-wider">
                    EMERGENCY CONTACTS & WHATSAPP ALERTS
                  </h3>
                  <p className="text-[11px] text-surface-400">
                    Send your emergency location & call your primary + trusted contacts.
                  </p>
                </div>
              </div>
              <span className="text-[10px] font-bold px-2.5 py-1 rounded-lg bg-emerald-950/80 text-emerald-300 border border-emerald-500/40">
                Option A: Direct Deep-Link
              </span>
            </div>

            <div className="space-y-3">
              {/* Primary Emergency Contact */}
              <div className="p-4 rounded-xl bg-surface-900/90 border border-surface-700/80 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="space-y-0.5">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-pink-500/20 text-pink-300 border border-pink-500/30 uppercase tracking-wider">
                      Primary Emergency Contact
                    </span>
                    {hasMobile ? (
                      <p className="text-xs font-mono font-bold text-surface-100 pt-1">
                        +91 {overview.emergency_profile.emergency_mobile}
                      </p>
                    ) : (
                      <p className="text-xs font-semibold text-rose-400 pt-1">
                        No emergency WhatsApp contact is configured.
                      </p>
                    )}
                  </div>

                  {hasMobile && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={() => handleTriggerWhatsApp(overview.emergency_profile.emergency_mobile, 'primary', 'Primary Contact')}
                        className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-98 text-white text-xs font-bold transition-all shadow-md cursor-pointer"
                        id="send-primary-whatsapp-btn"
                      >
                        <span>📱</span>
                        <span>{whatsappStatus['primary']?.status === 'opened' ? 'WhatsApp Opened' : 'OPEN WHATSAPP'}</span>
                      </button>

                      <button
                        onClick={() => handleInitiateCall(overview.emergency_profile.emergency_mobile, 'Primary Contact', 'PRIMARY')}
                        className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 active:scale-98 text-white text-xs font-bold transition-all shadow-md cursor-pointer"
                        id="call-primary-btn"
                      >
                        <HiPhone className="w-3.5 h-3.5" />
                        <span>CALL</span>
                      </button>

                      {whatsappStatus['primary']?.status === 'opened' && (
                        <button
                          onClick={() => handleConfirmAlertSent('Primary Contact', 'primary', overview.emergency_profile.emergency_mobile)}
                          className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 active:scale-98 text-white text-xs font-black transition-all shadow-md cursor-pointer animate-pulse"
                          id="confirm-sent-primary-btn"
                        >
                          <span>✓</span>
                          <span>I SENT THE ALERT</span>
                        </button>
                      )}
                    </div>
                  )}
                </div>

                {whatsappStatus['primary'] && (
                  <div className={`p-2.5 rounded-lg text-xs font-medium flex items-center gap-2 ${
                    whatsappStatus['primary'].status === 'confirmed'
                      ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/50'
                      : whatsappStatus['primary'].status === 'opened'
                      ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/30'
                      : whatsappStatus['primary'].status === 'copied'
                      ? 'bg-cyan-950/60 text-cyan-300 border border-cyan-500/30'
                      : 'bg-rose-950/60 text-rose-300 border border-rose-500/30'
                  }`}>
                    <span>{whatsappStatus['primary'].status === 'confirmed' ? '✅' : whatsappStatus['primary'].status === 'opened' ? '✓' : '📋'}</span>
                    <span>{whatsappStatus['primary'].message}</span>
                  </div>
                )}
              </div>

              {/* Trusted Contacts */}
              {contacts.length > 0 && (
                <div className="space-y-2 pt-1">
                  <span className="text-[11px] font-bold text-surface-400 uppercase tracking-wider block">
                    Trusted Contacts ({contacts.length})
                  </span>
                  <div className="grid grid-cols-1 gap-2.5">
                    {contacts.map((contact) => {
                      const cKey = `contact_${contact.id}`;
                      const validNum = contact.whatsapp_number || contact.mobile_number;
                      const hasValid = Boolean(validNum && normalizePhoneNumber(validNum));
                      const statusObj = whatsappStatus[cKey];

                      return (
                        <div
                          key={contact.id}
                          className="p-3.5 rounded-xl bg-surface-900/80 border border-surface-700/70 space-y-2.5"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div className="space-y-0.5">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-bold text-surface-200">👤 {contact.contact_name}</span>
                                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                                  {contact.relationship}
                                </span>
                              </div>
                              <p className="text-xs font-mono text-surface-300">
                                {hasValid ? `+91 ${validNum}` : <span className="text-amber-400 font-sans">WhatsApp unavailable — no valid mobile number configured.</span>}
                              </p>
                            </div>

                            {hasValid && (
                              <div className="flex items-center gap-2 flex-wrap">
                                <button
                                  onClick={() => handleTriggerWhatsApp(validNum, cKey, contact.contact_name)}
                                  className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-98 text-white text-xs font-bold transition-all shadow-sm cursor-pointer"
                                  id={`send-whatsapp-contact-${contact.id}`}
                                >
                                  <span>📱</span>
                                  <span>{statusObj?.status === 'opened' ? 'WhatsApp Opened' : 'OPEN WHATSAPP'}</span>
                                </button>

                                <button
                                  onClick={() => handleInitiateCall(validNum, contact.contact_name, 'TRUSTED')}
                                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 active:scale-98 text-white text-xs font-bold transition-all shadow-sm cursor-pointer"
                                  id={`call-contact-${contact.id}`}
                                >
                                  <HiPhone className="w-3.5 h-3.5" />
                                  <span>CALL</span>
                                </button>

                                {statusObj?.status === 'opened' && (
                                  <button
                                    onClick={() => handleConfirmAlertSent(contact.contact_name, cKey, validNum)}
                                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 active:scale-98 text-white text-xs font-black transition-all shadow-sm cursor-pointer animate-pulse"
                                    id={`confirm-sent-contact-${contact.id}`}
                                  >
                                    <span>✓</span>
                                    <span>I SENT THE ALERT</span>
                                  </button>
                                )}
                              </div>
                            )}
                          </div>

                          {statusObj && (
                            <div className={`p-2 rounded-lg text-xs font-medium flex items-center gap-2 ${
                              statusObj.status === 'confirmed'
                                ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/50'
                                : statusObj.status === 'opened'
                                ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/30'
                                : statusObj.status === 'copied'
                                ? 'bg-cyan-950/60 text-cyan-300 border border-cyan-500/30'
                                : 'bg-rose-950/60 text-rose-300 border border-rose-500/30'
                            }`}>
                              <span>{statusObj.status === 'confirmed' ? '✅' : statusObj.status === 'opened' ? '✓' : '📋'}</span>
                              <span>{statusObj.message}</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Instruction Notice */}
            <div className="p-3 rounded-xl bg-surface-950/60 border border-surface-800 text-[11px] text-surface-400 space-y-1">
              <p className="font-bold text-surface-200">📌 IMPORTANT NOTICE</p>
              <p>
                WhatsApp will open with the emergency message prepared. Press <span className="font-bold text-white">Send</span> inside WhatsApp to deliver the alert. Tap <span className="font-bold text-cyan-300">I SENT THE ALERT</span> after sending to confirm. NAVISCAPE never falsely claims delivery without your explicit confirmation.
              </p>
            </div>
          </div>

          {/* ── WS-3: EMERGENCY TIMELINE UI SECTION ──────────────── */}
          <div className="p-5 rounded-2xl bg-surface-950/80 border border-surface-800 space-y-4 pt-4 border-t">
            <div className="flex items-center justify-between border-b border-surface-800 pb-3">
              <div className="flex items-center gap-2.5">
                <span className="text-xl">📜</span>
                <div>
                  <h3 className="text-sm font-black text-white uppercase tracking-wider">
                    EMERGENCY TIMELINE & AUDIT TRAIL
                  </h3>
                  <p className="text-[11px] text-surface-400">
                    Real-time chronological log of emergency actions and status transitions.
                  </p>
                </div>
              </div>
              {loadingTimeline && (
                <div className="w-4 h-4 border-2 border-pink-500/30 border-t-pink-500 rounded-full animate-spin" />
              )}
            </div>

            {timeline.length === 0 ? (
              <p className="text-xs text-surface-500 italic p-4 text-center">No timeline actions logged yet.</p>
            ) : (
              <div className="space-y-3 relative pl-4 border-l-2 border-surface-800 ml-2">
                {timeline.map((item, idx) => {
                  let icon = '📍';
                  let colorClass = 'text-surface-200';

                  if (item.action_type === 'SOS_ACTIVATED') {
                    icon = '🔴';
                    colorClass = 'text-rose-400 font-bold';
                  } else if (item.action_type === 'GPS_CAPTURED') {
                    icon = '📍';
                    colorClass = 'text-cyan-400';
                  } else if (item.action_type === 'EMERGENCY_REGISTERED') {
                    icon = '✓';
                    colorClass = 'text-emerald-400';
                  } else if (item.action_type === 'WHATSAPP_OPENED') {
                    icon = '📱';
                    colorClass = 'text-emerald-300';
                  } else if (item.action_type === 'ALERT_SENT_CONFIRMED') {
                    icon = '✅';
                    colorClass = 'text-emerald-400 font-bold';
                  } else if (item.action_type === 'EMERGENCY_CONTACT_CALLED' || item.action_type === 'POLICE_CALLED') {
                    icon = '📞';
                    colorClass = 'text-amber-300 font-bold';
                  } else if (item.action_type === 'EMERGENCY_CANCELLED') {
                    icon = '🛑';
                    colorClass = 'text-rose-400';
                  } else if (item.action_type === 'EMERGENCY_RESOLVED') {
                    icon = '✅';
                    colorClass = 'text-emerald-400 font-black';
                  }

                  const formattedTime = formatActivationTime(item.created_at);

                  return (
                    <div key={item.id || idx} className="relative group">
                      <span className="absolute -left-[23px] top-1 w-3.5 h-3.5 rounded-full bg-surface-900 border-2 border-pink-500 text-[10px] flex items-center justify-center">
                        {icon}
                      </span>
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-xs">
                        <span className={`${colorClass} leading-tight`}>{item.description}</span>
                        <span className="text-[10px] font-mono text-surface-500 flex-shrink-0">{formattedTime}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* SOS TRIGGER CARD */
        <div className="glass-card p-6 border-2 border-rose-500/30 bg-gradient-to-br from-surface-900/90 via-surface-900/70 to-rose-950/20 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-surface-800 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-rose-500/20 text-rose-400 flex items-center justify-center font-bold">
                🚨
              </div>
              <div>
                <h2 className="text-sm font-bold text-surface-100 uppercase tracking-wider">Emergency SOS Trigger</h2>
                <p className="text-[11px] text-surface-400">Authenticated emergency protection mechanism</p>
              </div>
            </div>
            {!isProfileComplete && (
              <span className="text-[11px] font-bold text-amber-400 bg-amber-950/50 px-2.5 py-1 rounded-lg border border-amber-500/30">
                ⚠️ Setup Required to Activate SOS
              </span>
            )}
          </div>

          <div className="flex flex-col md:flex-row items-center justify-between gap-6 py-2">
            <div className="space-y-2 max-w-lg text-left">
              <h3 className="text-base font-black text-white">Press & Hold for 3 Seconds to Trigger SOS</h3>
              <p className="text-xs text-surface-300 leading-relaxed">
                To prevent accidental triggers, the SOS button requires a continuous 3-second hold followed by explicit
                confirmation. Once confirmed, NAVISCAPE captures your live GPS coordinates and initiates an emergency session.
              </p>
              {!isProfileComplete && (
                <p className="text-xs font-semibold text-rose-400">
                  * You must complete your Women Safety profile (Emergency Mobile, Location Consent, and 2+ Contacts) before SOS can be activated.
                </p>
              )}
            </div>

            {/* 3-Second Hold Trigger Button */}
            <div className="flex flex-col items-center gap-2 flex-shrink-0">
              <div className="relative">
                {/* SVG Circular Progress Ring */}
                <svg className="w-36 h-36 transform -rotate-90 pointer-events-none">
                  <circle
                    cx="72"
                    cy="72"
                    r="64"
                    stroke="currentColor"
                    strokeWidth="6"
                    className="text-surface-800"
                    fill="transparent"
                  />
                  <circle
                    cx="72"
                    cy="72"
                    r="64"
                    stroke="currentColor"
                    strokeWidth="6"
                    className={`transition-all duration-75 ${
                      isProfileComplete ? 'text-rose-500' : 'text-surface-600'
                    }`}
                    fill="transparent"
                    strokeDasharray={2 * Math.PI * 64}
                    strokeDashoffset={2 * Math.PI * 64 * (1 - holdProgress / 100)}
                    strokeLinecap="round"
                  />
                </svg>

                {/* Interactive SOS Trigger Button */}
                <button
                  onMouseDown={startHold}
                  onMouseUp={cancelHold}
                  onMouseLeave={cancelHold}
                  onTouchStart={startHold}
                  onTouchEnd={cancelHold}
                  onTouchCancel={cancelHold}
                  onPointerDown={startHold}
                  onPointerUp={cancelHold}
                  onPointerLeave={cancelHold}
                  onPointerCancel={cancelHold}
                  disabled={!isProfileComplete || activatingSos}
                  className={`
                    absolute inset-3 rounded-full flex flex-col items-center justify-center text-center select-none shadow-2xl transition-transform active:scale-95
                    ${
                      !isProfileComplete
                        ? 'bg-surface-800 text-surface-500 cursor-not-allowed border border-surface-700'
                        : isHolding
                        ? 'bg-gradient-to-br from-red-600 to-rose-700 text-white shadow-rose-600/50 ring-4 ring-rose-500/40 scale-95'
                        : 'bg-gradient-to-br from-rose-600 to-red-700 text-white hover:from-rose-500 hover:to-red-600 shadow-rose-900/60 ring-2 ring-rose-500/50'
                    }
                  `}
                  title={isProfileComplete ? 'Press and hold for 3 seconds' : 'Complete profile to enable SOS'}
                >
                  <span className="text-2xl mb-0.5">🚨</span>
                  <span className="text-sm font-black tracking-wider">EMERGENCY</span>
                  <span className="text-[10px] font-extrabold uppercase tracking-widest text-rose-200">SOS</span>
                </button>
              </div>

              {/* Dynamic Hold Status Text */}
              <p className="text-xs font-bold text-surface-300">
                {isHolding
                  ? `Hold for ${remainingSeconds} second${remainingSeconds > 1 ? 's' : ''}...`
                  : isProfileComplete
                  ? 'Press and hold for 3 seconds'
                  : 'Profile incomplete'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── MAIN CONTENT GRID (WS-1 PROFILE & CONTACTS) ────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: Emergency Profile & Trusted Contacts (8 cols) */}
        <div className="lg:col-span-8 space-y-6">
          {/* 1. EMERGENCY PROFILE CARD */}
          <div className="glass-card p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-surface-700/50 pb-3">
              <div className="flex items-center gap-2.5">
                <HiPhone className="w-5 h-5 text-pink-400" />
                <h2 className="text-sm font-bold text-surface-100 uppercase tracking-wider">Emergency Profile</h2>
              </div>
              <span className="text-[11px] font-semibold text-surface-400">Primary Contact & Preferences</span>
            </div>

            <form onSubmit={handleSaveProfile} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Emergency Mobile */}
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-surface-300">
                    Emergency Mobile Number <span className="text-pink-400">*</span>
                  </label>
                  <div className="relative">
                    <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-xs font-bold text-surface-500">
                      +91
                    </span>
                    <input
                      type="tel"
                      placeholder="9876543210"
                      value={emergencyMobile}
                      onChange={(e) => setEmergencyMobile(e.target.value)}
                      className="input-field pl-12 text-xs font-medium"
                      maxLength={14}
                    />
                  </div>
                  <p className="text-[11px] text-surface-500">10-digit Indian mobile number</p>
                </div>

                {/* Emergency Email */}
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-surface-300">
                    Emergency Email Address <span className="text-surface-500">(Optional)</span>
                  </label>
                  <div className="relative">
                    <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-surface-500">
                      <HiMail className="w-4 h-4" />
                    </span>
                    <input
                      type="email"
                      placeholder="emergency@example.com"
                      value={emergencyEmail}
                      onChange={(e) => setEmergencyEmail(e.target.value)}
                      className="input-field pl-10 text-xs font-medium"
                    />
                  </div>
                  <p className="text-[11px] text-surface-500">For secondary safety notifications</p>
                </div>
              </div>

              {/* Location Sharing Consent Control */}
              <div className="p-4 rounded-xl bg-surface-900/60 border border-surface-700/60 space-y-2">
                <label className="flex items-start gap-3 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                    className="mt-0.5 w-4 h-4 rounded text-pink-500 bg-surface-800 border-surface-600 focus:ring-pink-500 focus:ring-offset-surface-900 cursor-pointer"
                  />
                  <div className="space-y-1">
                    <p className="text-xs font-bold text-surface-100">
                      Allow NAVISCAPE to share my current location with my trusted contacts during an emergency.
                    </p>
                    <p className="text-[11px] text-surface-400">
                      Location-sharing consent is required before your Women Safety profile is marked as complete.
                      Consent defaults to disabled and can be revoked at any time.
                    </p>
                  </div>
                </label>
              </div>

              {/* Save Button */}
              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={savingProfile}
                  className="btn-primary !bg-pink-600 hover:!bg-pink-500 flex items-center gap-2 text-xs font-bold px-5 py-2.5"
                >
                  {savingProfile ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      <span>Saving Profile...</span>
                    </>
                  ) : (
                    <>
                      <HiShieldCheck className="w-4 h-4" />
                      <span>Save Emergency Profile</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* 2. TRUSTED CONTACTS CARD */}
          <div className="glass-card p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-surface-700/50 pb-3">
              <div className="flex items-center gap-2.5">
                <HiUserGroup className="w-5 h-5 text-cyan-400" />
                <div>
                  <h2 className="text-sm font-bold text-surface-100 uppercase tracking-wider">Trusted Contacts</h2>
                  <p className="text-[11px] text-surface-400">Add 2–4 people you trust for emergency alerts.</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`text-xs font-bold px-2.5 py-1 rounded-lg border ${
                    contactsCount >= 2
                      ? 'bg-cyan-950/60 text-cyan-300 border-cyan-500/40'
                      : 'bg-amber-950/40 text-amber-300 border-amber-500/30'
                  }`}
                >
                  {contactsCount} / 4 Contacts
                </span>
                <button
                  onClick={handleOpenAddModal}
                  disabled={contactsCount >= 4}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all shadow-sm ${
                    contactsCount >= 4
                      ? 'bg-surface-800 text-surface-500 cursor-not-allowed border border-surface-700'
                      : 'bg-cyan-600 hover:bg-cyan-500 text-white'
                  }`}
                  title={contactsCount >= 4 ? 'Maximum 4 contacts reached' : 'Add a new trusted contact'}
                >
                  <HiPlus className="w-4 h-4" />
                  <span>Add Contact</span>
                </button>
              </div>
            </div>

            {/* Contact List */}
            {contacts.length === 0 ? (
              <div className="text-center py-8 px-4 rounded-xl border border-dashed border-surface-700 bg-surface-900/40 space-y-3">
                <div className="w-12 h-12 mx-auto rounded-full bg-surface-800 text-surface-400 flex items-center justify-center">
                  <HiUserGroup className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-xs font-bold text-surface-200">No Trusted Contacts Added Yet</p>
                  <p className="text-[11px] text-surface-500 max-w-sm mx-auto mt-1">
                    Please add at least 2 trusted contacts so NAVISCAPE can alert them in case of emergency.
                  </p>
                </div>
                <button
                  onClick={handleOpenAddModal}
                  className="btn-secondary text-xs !py-2 !px-4 inline-flex items-center gap-1.5"
                >
                  <HiPlus className="w-4 h-4 text-cyan-400" />
                  <span>Add First Contact</span>
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {contacts.map((contact, idx) => (
                  <div
                    key={contact.id}
                    className="p-4 rounded-xl bg-surface-900/70 border border-surface-700/60 hover:border-cyan-500/40 transition-all space-y-3 relative group"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-black flex items-center justify-center">
                            {idx + 1}
                          </span>
                          <h3 className="text-xs font-bold text-surface-100">{contact.contact_name}</h3>
                        </div>
                        <span className="inline-block mt-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-pink-500/10 text-pink-300 border border-pink-500/20">
                          {contact.relationship}
                        </span>
                      </div>
                      {/* Action buttons */}
                      <div className="flex items-center gap-1 opacity-90 group-hover:opacity-100">
                        <button
                          onClick={() => handleOpenEditModal(contact)}
                          className="p-1.5 rounded-lg bg-surface-800 text-surface-300 hover:text-cyan-300 hover:bg-surface-700 transition-colors"
                          title="Edit contact"
                        >
                          <HiPencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setContactToDelete(contact)}
                          className="p-1.5 rounded-lg bg-surface-800 text-surface-300 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                          title="Delete contact"
                        >
                          <HiTrash className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    <div className="space-y-1 pt-1 border-t border-surface-800 text-[11px] text-surface-400">
                      <div className="flex items-center gap-2">
                        <HiPhone className="w-3.5 h-3.5 text-surface-500" />
                        <span className="font-mono text-surface-200">+91 {contact.mobile_number}</span>
                      </div>
                      {contact.email && (
                        <div className="flex items-center gap-2 truncate">
                          <HiMail className="w-3.5 h-3.5 text-surface-500 flex-shrink-0" />
                          <span className="truncate">{contact.email}</span>
                        </div>
                      )}
                      {/* WS-3A: WhatsApp indicator */}
                      {contact.whatsapp_number ? (
                        <div className="flex items-center gap-2">
                          <span className="text-[10px]">📱</span>
                          <span className="font-mono text-surface-200">WA: +91 {contact.whatsapp_number}</span>
                          {contact.whatsapp_alert_consent ? (
                            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">ALERTS ON</span>
                          ) : (
                            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-surface-800 text-surface-500 border border-surface-700">ALERTS OFF</span>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: Profile Status Panel & Requirements Checklist (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          <div className="glass-card p-6 space-y-5">
            <div className="border-b border-surface-700/50 pb-3">
              <h2 className="text-sm font-bold text-surface-100 uppercase tracking-wider">Profile Status</h2>
              <p className="text-[11px] text-surface-400">Readiness verification checklist</p>
            </div>

            {/* Checklist */}
            <div className="space-y-3">
              {/* 1. Trusted Contacts Count */}
              <div className="flex items-start gap-3 p-3 rounded-xl bg-surface-900/60 border border-surface-800">
                {contactsCount >= 2 ? (
                  <HiCheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
                ) : (
                  <HiXCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-surface-200">Trusted Contacts</span>
                    <span
                      className={`font-bold text-[11px] ${
                        contactsCount >= 2 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {contactsCount} / 4
                    </span>
                  </div>
                  <p className="text-[11px] text-surface-400 mt-0.5">
                    {contactsCount >= 2
                      ? 'Minimum requirement satisfied (2+ contacts).'
                      : `Add ${2 - contactsCount} more contact${2 - contactsCount > 1 ? 's' : ''} to complete.`}
                  </p>
                </div>
              </div>

              {/* 2. Emergency Mobile */}
              <div className="flex items-start gap-3 p-3 rounded-xl bg-surface-900/60 border border-surface-800">
                {hasMobile ? (
                  <HiCheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
                ) : (
                  <HiXCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-surface-200">Emergency Mobile</span>
                    <span className={`font-bold text-[11px] ${hasMobile ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {hasMobile ? 'Configured' : 'Missing'}
                    </span>
                  </div>
                  <p className="text-[11px] text-surface-400 mt-0.5">
                    {hasMobile ? '+91 ' + overview?.emergency_profile?.emergency_mobile : 'Please enter your emergency mobile number.'}
                  </p>
                </div>
              </div>

              {/* 3. Location Sharing Consent */}
              <div className="flex items-start gap-3 p-3 rounded-xl bg-surface-900/60 border border-surface-800">
                {hasConsent ? (
                  <HiCheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
                ) : (
                  <HiXCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-surface-200">Location Consent</span>
                    <span className={`font-bold text-[11px] ${hasConsent ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {hasConsent ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                  <p className="text-[11px] text-surface-400 mt-0.5">
                    {hasConsent
                      ? 'Consent granted for emergency location sharing.'
                      : 'Explicit consent is required for profile readiness.'}
                  </p>
                </div>
              </div>
            </div>

            {/* Summary Box */}
            <div
              className={`p-4 rounded-xl border text-center space-y-1.5 ${
                isProfileComplete
                  ? 'bg-gradient-to-br from-emerald-950/60 to-emerald-900/20 border-emerald-500/40 text-emerald-300'
                  : 'bg-gradient-to-br from-surface-900 to-surface-800/40 border-surface-700 text-surface-300'
              }`}
            >
              <span className="text-[10px] font-bold uppercase tracking-wider text-surface-400">Overall Protection State</span>
              <p className="text-sm font-black tracking-tight">
                {isProfileComplete ? 'PROTECTION PROFILE READY' : 'PROFILE SETUP INCOMPLETE'}
              </p>
              <p className="text-[11px] text-surface-400">
                {isProfileComplete
                  ? 'All foundational requirements are fulfilled. Your profile is ready for emergency SOS triggers.'
                  : 'Complete all 3 requirements above to activate your emergency safety profile.'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── WS-2 MODAL: CONFIRM EMERGENCY ACTIVATION ───────────────────────── */}
      {isConfirmSosModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-surface-950/80 backdrop-blur-md animate-fadeIn">
          <div className="glass-card w-full max-w-md p-6 space-y-5 border-2 border-rose-500/60 shadow-2xl bg-surface-900 text-left">
            <div className="flex items-center gap-3 border-b border-surface-800 pb-3">
              <div className="w-10 h-10 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center text-xl flex-shrink-0">
                🚨
              </div>
              <div>
                <h3 className="text-base font-black text-white">CONFIRM EMERGENCY</h3>
                <p className="text-xs text-rose-300 font-medium">Activate Emergency SOS Session</p>
              </div>
            </div>

            <div className="space-y-3 text-xs text-surface-300 leading-relaxed">
              <p className="font-semibold text-surface-100">
                Are you sure you want to activate emergency mode?
              </p>
              <p>
                NAVISCAPE will immediately capture your current device GPS coordinates and register an active emergency
                event on the server.
              </p>
              <div className="p-3 rounded-xl bg-surface-950/70 border border-surface-800 text-[11px] text-surface-400">
                <span className="font-bold text-rose-400">Notice:</span> Browser location permission is required. NAVISCAPE will obtain your live device coordinates via GPS.
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsConfirmSosModalOpen(false)}
                disabled={activatingSos}
                className="btn-secondary text-xs !py-2.5 !px-5 font-bold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                CANCEL
              </button>
              <button
                type="button"
                onClick={handleConfirmSOS}
                disabled={activatingSos}
                className="btn-primary !bg-rose-600 hover:!bg-rose-500 text-xs !py-2.5 !px-6 font-black tracking-wider shadow-lg shadow-rose-950/50 flex items-center gap-2 disabled:opacity-75 disabled:cursor-not-allowed"
                id="confirm-emergency-btn"
              >
                {activatingSos ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>{sosPhaseText || 'Getting your current location...'}</span>
                  </>
                ) : (
                  <span>CONFIRM EMERGENCY</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── WS-2 MODAL: CANCEL ACTIVE EMERGENCY ────────────────────────────── */}
      {isCancelModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-surface-950/80 backdrop-blur-md animate-fadeIn">
          <div className="glass-card w-full max-w-md p-6 space-y-4 border border-surface-700 shadow-2xl bg-surface-900 text-left">
            <div className="w-12 h-12 rounded-full bg-surface-800 text-surface-200 flex items-center justify-center mx-auto text-xl">
              🛑
            </div>
            <div className="text-center space-y-1">
              <h3 className="text-base font-bold text-white">Cancel Emergency?</h3>
              <p className="text-xs text-surface-400">
                Are you sure you want to end this active emergency session?
              </p>
            </div>

            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsCancelModalOpen(false)}
                className="btn-secondary text-xs !py-2.5 !px-5 font-bold"
              >
                Keep Active
              </button>
              <button
                type="button"
                onClick={handleConfirmCancelEmergency}
                disabled={cancellingEmergency}
                className="btn-primary !bg-rose-600 hover:!bg-rose-500 text-xs !py-2.5 !px-6 font-bold flex items-center gap-2"
              >
                {cancellingEmergency ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Cancelling...</span>
                  </>
                ) : (
                  <span>Cancel Emergency</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── WS-3 MODAL: RESOLVE ACTIVE EMERGENCY ────────────────────────────── */}
      {isResolveModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-surface-950/80 backdrop-blur-md animate-fadeIn">
          <div className="glass-card w-full max-w-md p-6 space-y-4 border border-emerald-500/40 shadow-2xl bg-surface-900 text-left">
            <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center mx-auto text-2xl">
              ✅
            </div>
            <div className="text-center space-y-1">
              <h3 className="text-base font-bold text-white">Resolve Emergency?</h3>
              <p className="text-xs text-surface-400">
                Are you sure the emergency has been resolved?
              </p>
            </div>

            <div className="p-3 rounded-xl bg-surface-950/70 border border-surface-800 text-[11px] text-surface-400 text-center">
              This will change the emergency status to <span className="font-bold text-emerald-300">RESOLVED</span> and log the resolution in your audit history.
            </div>

            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsResolveModalOpen(false)}
                className="btn-secondary text-xs !py-2.5 !px-5 font-bold"
              >
                Keep Active
              </button>
              <button
                type="button"
                onClick={handleConfirmResolveEmergency}
                disabled={resolvingEmergency}
                className="btn-primary !bg-emerald-600 hover:!bg-emerald-500 text-xs !py-2.5 !px-6 font-bold flex items-center gap-2 cursor-pointer shadow-lg shadow-emerald-950/50"
                id="confirm-resolve-btn"
              >
                {resolvingEmergency ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Resolving...</span>
                  </>
                ) : (
                  <span>YES, RESOLVE EMERGENCY</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── WS-1 MODAL: ADD / EDIT TRUSTED CONTACT ─────────────────────────── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-surface-950/80 backdrop-blur-sm animate-fadeIn">
          <div className="glass-card w-full max-w-md p-6 space-y-5 border border-surface-700 shadow-2xl bg-surface-900">
            <div className="flex items-center justify-between border-b border-surface-800 pb-3">
              <h3 className="text-sm font-bold text-surface-100 flex items-center gap-2">
                <HiUserGroup className="w-5 h-5 text-cyan-400" />
                {editingContactId ? 'Edit Trusted Contact' : 'Add Trusted Contact'}
              </h3>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1 rounded-lg text-surface-400 hover:text-surface-100 hover:bg-surface-800 transition-colors"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveContact} className="space-y-4">
              {/* Contact Name */}
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-surface-300">
                  Full Name <span className="text-pink-400">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Aarav Sharma"
                  value={contactName}
                  onChange={(e) => setContactName(e.target.value)}
                  className="input-field text-xs"
                  maxLength={100}
                  required
                />
              </div>

              {/* Relationship */}
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-surface-300">
                  Relationship <span className="text-pink-400">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Mother, Father, Brother, Friend"
                  value={relationship}
                  onChange={(e) => setRelationship(e.target.value)}
                  className="input-field text-xs"
                  maxLength={50}
                  required
                />
              </div>

              {/* Mobile Number */}
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-surface-300">
                  Mobile Number <span className="text-pink-400">*</span>
                </label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-xs font-bold text-surface-500">
                    +91
                  </span>
                  <input
                    type="tel"
                    placeholder="9876543210"
                    value={contactMobile}
                    onChange={(e) => setContactMobile(e.target.value)}
                    className="input-field pl-12 text-xs"
                    maxLength={14}
                    required
                  />
                </div>
                <p className="text-[10px] text-surface-500">10-digit Indian mobile number</p>
              </div>

              {/* Email */}
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-surface-300">
                  Email Address <span className="text-surface-500">(Optional)</span>
                </label>
                <input
                  type="email"
                  placeholder="contact@example.com"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                  className="input-field text-xs"
                />
              </div>

              {/* WS-3A: WhatsApp Number */}
              <div className="space-y-1">
                <label className="block text-xs font-semibold text-surface-300">
                  WhatsApp Number <span className="text-surface-500">(Optional)</span>
                </label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-xs font-bold text-surface-500">
                    +91
                  </span>
                  <input
                    type="tel"
                    placeholder="9876543210"
                    value={contactWhatsApp}
                    onChange={(e) => setContactWhatsApp(e.target.value)}
                    className="input-field pl-12 text-xs"
                    maxLength={14}
                  />
                </div>
                <p className="text-[10px] text-surface-500">10-digit Indian WhatsApp number for emergency alerts</p>
              </div>

              {/* WS-3A: WhatsApp Alert Consent */}
              <div className="p-3 rounded-xl bg-surface-900/60 border border-surface-700/60">
                <label className="flex items-start gap-3 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={contactWhatsAppConsent}
                    onChange={(e) => setContactWhatsAppConsent(e.target.checked)}
                    className="mt-0.5 w-4 h-4 rounded text-emerald-500 bg-surface-800 border-surface-600 focus:ring-emerald-500 focus:ring-offset-surface-900 cursor-pointer"
                  />
                  <div className="space-y-0.5">
                    <p className="text-xs font-bold text-surface-100">
                      Allow emergency alerts through WhatsApp
                    </p>
                    <p className="text-[10px] text-surface-500">
                      When enabled, you can send a pre-filled emergency message to this contact via WhatsApp during an active SOS.
                    </p>
                  </div>
                </label>
              </div>

              {/* Buttons */}
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="btn-secondary text-xs !py-2 !px-4"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingContact}
                  className="btn-primary !bg-cyan-600 hover:!bg-cyan-500 text-xs !py-2 !px-5 font-bold flex items-center gap-2"
                >
                  {savingContact ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      <span>Saving...</span>
                    </>
                  ) : (
                    <span>{editingContactId ? 'Update Contact' : 'Save Contact'}</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── WS-1 MODAL: DELETE CONFIRMATION ────────────────────────────────── */}
      {contactToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-surface-950/80 backdrop-blur-sm animate-fadeIn">
          <div className="glass-card w-full max-w-sm p-6 space-y-4 border border-rose-500/30 shadow-2xl bg-surface-900">
            <div className="w-10 h-10 rounded-full bg-rose-500/10 text-rose-400 flex items-center justify-center mx-auto">
              <HiTrash className="w-5 h-5" />
            </div>
            <div className="text-center space-y-1">
              <h3 className="text-sm font-bold text-surface-100">Remove Trusted Contact?</h3>
              <p className="text-xs text-surface-400">
                Are you sure you want to remove <span className="text-surface-200 font-semibold">{contactToDelete.contact_name}</span> from your trusted contacts?
              </p>
            </div>
            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setContactToDelete(null)}
                className="btn-secondary text-xs !py-2 !px-4"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={deletingContact}
                className="btn-primary !bg-rose-600 hover:!bg-rose-500 text-xs !py-2 !px-5 font-bold flex items-center gap-2"
              >
                {deletingContact ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Removing...</span>
                  </>
                ) : (
                  <span>Yes, Remove</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
