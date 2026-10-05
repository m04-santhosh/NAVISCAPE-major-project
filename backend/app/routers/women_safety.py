"""
NAVISCAPE Women Safety — Emergency Profile, Trusted Contacts & SOS Events Router
Provides secure, tenant-isolated endpoints for managing emergency profiles, trusted contacts,
and authenticated emergency SOS events.
"""

from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

import logging
from ..database import get_db

logger = logging.getLogger(__name__)

from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.emergency_profile import EmergencyProfile, TrustedContact
from ..models.emergency_event import EmergencyEvent
from ..models.emergency_action import EmergencyAction
import json

from ..schemas.emergency_profile import (
    EmergencyProfileUpdate,
    EmergencyProfileResponse,
    TrustedContactCreate,
    TrustedContactUpdate,
    TrustedContactResponse,
    WomenSafetyOverviewResponse,
)
from ..schemas.emergency_event import (
    EmergencyEventCreate,
    EmergencyEventResponse,
    ActiveEmergencyResponse,
)
from ..schemas.emergency import (
    EmergencyTriggerRequest,
    EmergencyTriggerResponse,
)
from ..schemas.emergency_action import (
    EmergencyActionCreate,
    EmergencyActionResponse,
    EmergencyTimelineResponse,
    TimelineItemResponse,
    StatusUpdateRequest,
)

router = APIRouter(
    prefix="/api/women-safety",
    tags=["Women Safety"],
)


def _compute_overview(profile: EmergencyProfile | None, contacts: List[TrustedContact]) -> WomenSafetyOverviewResponse:
    """Helper to construct authoritative overview and readiness status."""
    has_mobile = bool(profile and profile.emergency_mobile and profile.emergency_mobile.strip())
    consent = bool(profile and profile.location_sharing_consent)
    contacts_count = len(contacts)

    is_complete = has_mobile and consent and (contacts_count >= 2)

    profile_resp = EmergencyProfileResponse.model_validate(profile) if profile else None
    contacts_resp = [TrustedContactResponse.model_validate(c) for c in contacts]

    return WomenSafetyOverviewResponse(
        emergency_profile=profile_resp,
        trusted_contacts=contacts_resp,
        profile_complete=is_complete,
        contacts_count=contacts_count,
        min_contacts_required=2,
        max_contacts_allowed=4,
        has_emergency_mobile=has_mobile,
        location_sharing_consent=consent,
    )


def _describe_action(action_type: str, contact_name: str | None = None, contact_type: str | None = None) -> str:
    """Helper to generate user-friendly description for emergency timeline actions."""
    c_name = contact_name or ("Emergency Contact" if contact_type == "PRIMARY" else "contact")
    mapping = {
        "SOS_ACTIVATED": "Emergency SOS activated",
        "GPS_CAPTURED": "Current GPS location captured",
        "EMERGENCY_REGISTERED": "Emergency event registered",
        "WHATSAPP_PREPARED": f"WhatsApp emergency alert prepared for {c_name}",
        "WHATSAPP_OPENED": f"WhatsApp opened for {c_name}",
        "ALERT_SENT_CONFIRMED": f"Alert sent confirmed for {c_name}",
        "EMERGENCY_CANCELLED": "Emergency session cancelled",
        "EMERGENCY_RESOLVED": "Emergency session marked as resolved",
        "EMERGENCY_CONTACT_CALLED": f"Emergency call initiated to {c_name}",
        "POLICE_CALLED": "Emergency call initiated to Police (112)",
    }
    return mapping.get(action_type, f"Action '{action_type}' recorded")


# ── Emergency Profile Endpoints ───────────────────────────────────────────────

@router.get(
    "/emergency-profile",
    response_model=WomenSafetyOverviewResponse,
    summary="Get authenticated user's emergency profile and trusted contacts overview",
)
async def get_emergency_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(EmergencyProfile).filter(EmergencyProfile.user_id == current_user.id).first()
    contacts = (
        db.query(TrustedContact)
        .filter(TrustedContact.user_id == current_user.id)
        .order_by(TrustedContact.created_at.asc())
        .all()
    )
    return _compute_overview(profile, contacts)


@router.put(
    "/emergency-profile",
    response_model=WomenSafetyOverviewResponse,
    summary="Create or update authenticated user's emergency profile",
)
@router.patch(
    "/emergency-profile",
    response_model=WomenSafetyOverviewResponse,
    summary="Create or update authenticated user's emergency profile (patch alias)",
)
async def update_emergency_profile(
    payload: EmergencyProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(EmergencyProfile).filter(EmergencyProfile.user_id == current_user.id).first()

    if profile is None:
        profile = EmergencyProfile(
            user_id=current_user.id,
            emergency_mobile=payload.emergency_mobile,
            emergency_email=payload.emergency_email,
            location_sharing_consent=payload.location_sharing_consent,
        )
        db.add(profile)
    else:
        if payload.emergency_mobile is not None:
            profile.emergency_mobile = payload.emergency_mobile
        if payload.emergency_email is not None:
            profile.emergency_email = payload.emergency_email
        profile.location_sharing_consent = payload.location_sharing_consent

    db.commit()
    db.refresh(profile)

    contacts = (
        db.query(TrustedContact)
        .filter(TrustedContact.user_id == current_user.id)
        .order_by(TrustedContact.created_at.asc())
        .all()
    )
    return _compute_overview(profile, contacts)


# ── Trusted Contacts Endpoints ────────────────────────────────────────────────

@router.post(
    "/trusted-contacts",
    response_model=TrustedContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new trusted contact",
)
async def add_trusted_contact(
    payload: TrustedContactCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_count = db.query(TrustedContact).filter(TrustedContact.user_id == current_user.id).count()
    if current_count >= 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum limit of 4 trusted contacts reached. You must remove an existing contact before adding a new one.",
        )

    contact = TrustedContact(
        user_id=current_user.id,
        contact_name=payload.contact_name,
        relationship=payload.relationship,
        mobile_number=payload.mobile_number,
        email=payload.email,
        whatsapp_number=payload.whatsapp_number,
        whatsapp_alert_consent=payload.whatsapp_alert_consent,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.put(
    "/trusted-contacts/{contact_id}",
    response_model=TrustedContactResponse,
    summary="Update a trusted contact",
)
@router.patch(
    "/trusted-contacts/{contact_id}",
    response_model=TrustedContactResponse,
    summary="Update a trusted contact (patch alias)",
)
async def update_trusted_contact(
    contact_id: int,
    payload: TrustedContactUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = (
        db.query(TrustedContact)
        .filter(TrustedContact.id == contact_id, TrustedContact.user_id == current_user.id)
        .first()
    )
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trusted contact not found.",
        )

    if payload.contact_name is not None:
        contact.contact_name = payload.contact_name
    if payload.relationship is not None:
        contact.relationship = payload.relationship
    if payload.mobile_number is not None:
        contact.mobile_number = payload.mobile_number
    if payload.email is not None:
        contact.email = payload.email
    if "whatsapp_number" in payload.model_fields_set:
        contact.whatsapp_number = payload.whatsapp_number
    if payload.whatsapp_alert_consent is not None:
        contact.whatsapp_alert_consent = payload.whatsapp_alert_consent

    db.commit()
    db.refresh(contact)
    return contact


@router.delete(
    "/trusted-contacts/{contact_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a trusted contact",
)
async def delete_trusted_contact(
    contact_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = (
        db.query(TrustedContact)
        .filter(TrustedContact.id == contact_id, TrustedContact.user_id == current_user.id)
        .first()
    )
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trusted contact not found.",
        )

    db.delete(contact)
    db.commit()
    return {
        "message": "Trusted contact deleted successfully.",
        "contact_id": contact_id,
    }


# ── WS-1, WS-2 & WS-3: SOS Trigger & Emergency Events Endpoints ───────────────

@router.post(
    "/emergency",
    response_model=EmergencyTriggerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="WS-1: Register an authenticated emergency event with real GPS coordinates",
)
async def trigger_emergency(
    payload: EmergencyTriggerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = EmergencyEvent(
        user_id=current_user.id,
        status="ACTIVE",
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_accuracy_m=payload.accuracy_m,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # WS-3 Audit Trail: Log initial emergency actions
    db.add_all([
        EmergencyAction(
            emergency_event_id=event.id,
            user_id=current_user.id,
            action_type="SOS_ACTIVATED",
            latitude=event.latitude,
            longitude=event.longitude,
        ),
        EmergencyAction(
            emergency_event_id=event.id,
            user_id=current_user.id,
            action_type="GPS_CAPTURED",
            latitude=event.latitude,
            longitude=event.longitude,
        ),
        EmergencyAction(
            emergency_event_id=event.id,
            user_id=current_user.id,
            action_type="EMERGENCY_REGISTERED",
            latitude=event.latitude,
            longitude=event.longitude,
        ),
    ])
    db.commit()

    return EmergencyTriggerResponse(
        success=True,
        emergency_id=str(event.id),
        id=event.id,
        latitude=event.latitude,
        longitude=event.longitude,
        accuracy_m=event.location_accuracy_m,
        triggered_at=event.triggered_at,
        status=event.status,
    )


@router.post(
    "/emergency-events",
    response_model=EmergencyEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an authenticated emergency event (SOS trigger)",
)
async def create_emergency_event(
    payload: EmergencyEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(EmergencyProfile).filter(EmergencyProfile.user_id == current_user.id).first()
    contacts_count = db.query(TrustedContact).filter(TrustedContact.user_id == current_user.id).count()

    has_mobile = bool(profile and profile.emergency_mobile and profile.emergency_mobile.strip())
    has_consent = bool(profile and profile.location_sharing_consent)
    is_profile_complete = has_mobile and has_consent and (contacts_count >= 2)

    if not is_profile_complete:
        missing_reasons = []
        if not has_mobile:
            missing_reasons.append("configure your emergency mobile number")
        if not has_consent:
            missing_reasons.append("grant location-sharing consent")
        if contacts_count < 2:
            missing_reasons.append(f"add at least 2 trusted contacts (currently {contacts_count}/2)")

        detail_msg = (
            f"Cannot activate emergency mode. Your Women Safety profile is incomplete. "
            f"Please {', and '.join(missing_reasons)} before activating SOS."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail_msg,
        )

    existing_active = (
        db.query(EmergencyEvent)
        .filter(
            EmergencyEvent.user_id == current_user.id,
            EmergencyEvent.status.in_(["ACTIVE", "ALERTS_PREPARED", "CONTACTS_NOTIFIED"]),
        )
        .first()
    )
    if existing_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active emergency session is already in progress for your account.",
        )

    event = EmergencyEvent(
        user_id=current_user.id,
        status="ACTIVE",
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_accuracy_m=payload.location_accuracy_m,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # WS-3 Audit Trail: Log initial emergency actions
    db.add_all([
        EmergencyAction(
            emergency_event_id=event.id,
            user_id=current_user.id,
            action_type="SOS_ACTIVATED",
            latitude=event.latitude,
            longitude=event.longitude,
        ),
        EmergencyAction(
            emergency_event_id=event.id,
            user_id=current_user.id,
            action_type="GPS_CAPTURED",
            latitude=event.latitude,
            longitude=event.longitude,
        ),
        EmergencyAction(
            emergency_event_id=event.id,
            user_id=current_user.id,
            action_type="EMERGENCY_REGISTERED",
            latitude=event.latitude,
            longitude=event.longitude,
        ),
    ])
    db.commit()

    return event


@router.get(
    "/emergency/active",
    response_model=ActiveEmergencyResponse,
    summary="Get authenticated user's current ACTIVE emergency event (WS-1 alias)",
)
@router.get(
    "/emergency-events/active",
    response_model=ActiveEmergencyResponse,
    summary="Get authenticated user's current ACTIVE emergency event",
)
async def get_active_emergency_event(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    active_event = (
        db.query(EmergencyEvent)
        .filter(
            EmergencyEvent.user_id == current_user.id,
            EmergencyEvent.status.in_(["ACTIVE", "ALERTS_PREPARED", "CONTACTS_NOTIFIED"]),
        )
        .order_by(EmergencyEvent.triggered_at.desc())
        .first()
    )
    if active_event:
        return ActiveEmergencyResponse(
            has_active_event=True,
            event=EmergencyEventResponse.model_validate(active_event),
        )
    return ActiveEmergencyResponse(has_active_event=False, event=None)


@router.post(
    "/emergency/{event_id}/cancel",
    response_model=EmergencyEventResponse,
    summary="Cancel an active emergency event (WS-1 alias)",
)
@router.patch(
    "/emergency/{event_id}/cancel",
    response_model=EmergencyEventResponse,
    summary="Cancel an active emergency event (WS-1 patch alias)",
)
@router.post(
    "/emergency-events/{event_id}/cancel",
    response_model=EmergencyEventResponse,
    summary="Cancel an active emergency event",
)
@router.patch(
    "/emergency-events/{event_id}/cancel",
    response_model=EmergencyEventResponse,
    summary="Cancel an active emergency event (patch alias)",
)
async def cancel_emergency_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = (
        db.query(EmergencyEvent)
        .filter(EmergencyEvent.id == event_id, EmergencyEvent.user_id == current_user.id)
        .first()
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency event not found.",
        )

    if event.status in ("ACTIVE", "ALERTS_PREPARED", "CONTACTS_NOTIFIED"):
        event.status = "CANCELLED"
        event.cancelled_at = func.now()
        db.add(
            EmergencyAction(
                emergency_event_id=event.id,
                user_id=current_user.id,
                action_type="EMERGENCY_CANCELLED",
                latitude=event.latitude,
                longitude=event.longitude,
            )
        )
        db.commit()
        db.refresh(event)

    return event


# ── WS-3: Emergency Actions, Timeline & Status Endpoints ─────────────────────

@router.post(
    "/emergency/{event_id}/actions",
    response_model=EmergencyActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an emergency action in the audit trail",
)
@router.post(
    "/emergency-events/{event_id}/actions",
    response_model=EmergencyActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an emergency action in the audit trail (alias)",
)
async def record_emergency_action(
    event_id: int,
    payload: EmergencyActionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = (
        db.query(EmergencyEvent)
        .filter(EmergencyEvent.id == event_id, EmergencyEvent.user_id == current_user.id)
        .first()
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency event not found.",
        )

    action_type = payload.action_type
    if action_type in ("WHATSAPP_OPENED", "WHATSAPP_PREPARED") and event.status == "ACTIVE":
        event.status = "ALERTS_PREPARED"
    elif action_type == "ALERT_SENT_CONFIRMED" and event.status in ("ACTIVE", "ALERTS_PREPARED"):
        event.status = "CONTACTS_NOTIFIED"
    elif action_type == "EMERGENCY_CANCELLED" and event.status != "CANCELLED":
        event.status = "CANCELLED"
        event.cancelled_at = func.now()
    elif action_type == "EMERGENCY_RESOLVED" and event.status != "RESOLVED":
        event.status = "RESOLVED"

    meta_str = json.dumps(payload.metadata) if payload.metadata else None

    action = EmergencyAction(
        emergency_event_id=event.id,
        user_id=current_user.id,
        action_type=action_type,
        contact_type=payload.contact_type,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        latitude=payload.latitude if payload.latitude is not None else event.latitude,
        longitude=payload.longitude if payload.longitude is not None else event.longitude,
        metadata_json=meta_str,
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    resp = EmergencyActionResponse.model_validate(action)
    resp.description = _describe_action(action.action_type, action.contact_name, action.contact_type)
    return resp


@router.get(
    "/emergency/{event_id}/timeline",
    response_model=EmergencyTimelineResponse,
    summary="Get chronological emergency actions timeline",
)
@router.get(
    "/emergency-events/{event_id}/timeline",
    response_model=EmergencyTimelineResponse,
    summary="Get chronological emergency actions timeline (alias)",
)
async def get_emergency_timeline(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = (
        db.query(EmergencyEvent)
        .filter(EmergencyEvent.id == event_id, EmergencyEvent.user_id == current_user.id)
        .first()
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency event not found.",
        )

    actions = (
        db.query(EmergencyAction)
        .filter(EmergencyAction.emergency_event_id == event.id, EmergencyAction.user_id == current_user.id)
        .order_by(EmergencyAction.created_at.asc(), EmergencyAction.id.asc())
        .all()
    )

    timeline_items = []
    if not actions:
        base_time = event.triggered_at or event.created_at
        timeline_items.append(
            TimelineItemResponse(
                id=1,
                action_type="SOS_ACTIVATED",
                contact_type=None,
                contact_name=None,
                contact_phone=None,
                created_at=base_time,
                description="Emergency SOS activated",
            )
        )
        timeline_items.append(
            TimelineItemResponse(
                id=2,
                action_type="GPS_CAPTURED",
                contact_type=None,
                contact_name=None,
                contact_phone=None,
                created_at=base_time,
                description="Current GPS location captured",
            )
        )
        timeline_items.append(
            TimelineItemResponse(
                id=3,
                action_type="EMERGENCY_REGISTERED",
                contact_type=None,
                contact_name=None,
                contact_phone=None,
                created_at=base_time,
                description="Emergency event registered",
            )
        )
        if event.status == "CANCELLED":
            timeline_items.append(
                TimelineItemResponse(
                    id=4,
                    action_type="EMERGENCY_CANCELLED",
                    contact_type=None,
                    contact_name=None,
                    contact_phone=None,
                    created_at=event.cancelled_at or base_time,
                    description="Emergency session cancelled",
                )
            )
        elif event.status == "RESOLVED":
            timeline_items.append(
                TimelineItemResponse(
                    id=4,
                    action_type="EMERGENCY_RESOLVED",
                    contact_type=None,
                    contact_name=None,
                    contact_phone=None,
                    created_at=event.updated_at or base_time,
                    description="Emergency session marked as resolved",
                )
            )
    else:
        for a in actions:
            desc = _describe_action(a.action_type, a.contact_name, a.contact_type)
            timeline_items.append(
                TimelineItemResponse(
                    id=a.id,
                    action_type=a.action_type,
                    contact_type=a.contact_type,
                    contact_name=a.contact_name,
                    contact_phone=a.contact_phone,
                    created_at=a.created_at,
                    description=desc,
                )
            )

    return EmergencyTimelineResponse(
        emergency_id=event.id,
        status=event.status,
        timeline=timeline_items,
    )


@router.patch(
    "/emergency/{event_id}/status",
    response_model=EmergencyEventResponse,
    summary="Update emergency event lifecycle status",
)
@router.patch(
    "/emergency-events/{event_id}/status",
    response_model=EmergencyEventResponse,
    summary="Update emergency event lifecycle status (alias)",
)
async def update_emergency_status(
    event_id: int,
    payload: StatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = (
        db.query(EmergencyEvent)
        .filter(EmergencyEvent.id == event_id, EmergencyEvent.user_id == current_user.id)
        .first()
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency event not found.",
        )

    new_status = payload.status
    if event.status != new_status:
        event.status = new_status
        if new_status == "CANCELLED":
            event.cancelled_at = func.now()

        action_map = {
            "CANCELLED": "EMERGENCY_CANCELLED",
            "RESOLVED": "EMERGENCY_RESOLVED",
            "CONTACTS_NOTIFIED": "ALERT_SENT_CONFIRMED",
            "ALERTS_PREPARED": "WHATSAPP_PREPARED",
        }
        if new_status in action_map:
            db.add(
                EmergencyAction(
                    emergency_event_id=event.id,
                    user_id=current_user.id,
                    action_type=action_map[new_status],
                    latitude=event.latitude,
                    longitude=event.longitude,
                )
            )

        db.commit()
        db.refresh(event)

    return event


# ── WS-2 & WS-3A: WhatsApp Emergency Alert URL Generator ────────────────────────

@router.get(
    "/emergency-events/{event_id}/whatsapp-alerts",
    summary="Generate WhatsApp click-to-chat URLs for an active emergency event",
)
async def get_whatsapp_alerts(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generates WhatsApp click-to-chat URLs for trusted contacts.

    Security constraints:
    - Event MUST belong to the authenticated user.
    - Event MUST have status == ACTIVE.
    - GPS coordinates come ONLY from the EmergencyEvent record.

    This endpoint is READ-ONLY. It does NOT send any messages, does NOT call
    external APIs, and does NOT mark anything as sent.
    """
    from ..services.whatsapp_service import (
        generate_emergency_message,
        generate_whatsapp_url,
        normalize_whatsapp_number,
    )

    # 1. Verify event belongs to authenticated user
    event = (
        db.query(EmergencyEvent)
        .filter(EmergencyEvent.id == event_id, EmergencyEvent.user_id == current_user.id)
        .first()
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency event not found.",
        )

    # 2. Verify event is ACTIVE
    if event.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WhatsApp alerts can only be generated for ACTIVE emergency events.",
        )

    # 3. Get trusted contacts for authenticated user
    contacts = (
        db.query(TrustedContact)
        .filter(TrustedContact.user_id == current_user.id)
        .order_by(TrustedContact.created_at.asc())
        .all()
    )

    user_name = current_user.email.split("@")[0] if current_user.email else "NAVISCAPE User"
    triggered_at_str = (
        event.triggered_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        if event.triggered_at
        else "Unknown"
    )

    alerts = []
    for contact in contacts:
        alert_entry = {
            "contact_id": contact.id,
            "contact_name": contact.contact_name,
            "relationship": contact.relationship,
            "whatsapp_number": contact.whatsapp_number,
            "whatsapp_alert_consent": contact.whatsapp_alert_consent,
        }

        # Check whatsapp_number / mobile_number and whatsapp_alert_consent
        raw_num = contact.whatsapp_number or contact.mobile_number

        if raw_num and contact.whatsapp_alert_consent:
            try:
                norm_num = normalize_whatsapp_number(raw_num)
                msg = generate_emergency_message(
                    user_name=user_name,
                    latitude=event.latitude,
                    longitude=event.longitude,
                    accuracy_m=event.location_accuracy_m,
                    triggered_at=triggered_at_str,
                )
                wa_url = generate_whatsapp_url(norm_num, msg)
                alert_entry["whatsapp_available"] = True
                alert_entry["whatsapp_url"] = wa_url
                alert_entry["message_preview"] = msg
            except ValueError:
                alert_entry["whatsapp_available"] = False
                alert_entry["whatsapp_url"] = None
                alert_entry["message_preview"] = None
                alert_entry["reason"] = "WhatsApp alert unavailable for this contact."
        else:
            alert_entry["whatsapp_available"] = False
            alert_entry["whatsapp_url"] = None
            alert_entry["message_preview"] = None
            alert_entry["reason"] = "WhatsApp alert unavailable for this contact."

        alerts.append(alert_entry)

    return {
        "event_id": event.id,
        "event_status": event.status,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "accuracy_m": event.location_accuracy_m,
        "triggered_at": triggered_at_str,
        "alerts": alerts,
    }
