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

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.emergency_profile import EmergencyProfile, TrustedContact
from ..models.emergency_event import EmergencyEvent
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

router = APIRouter(
    prefix="/api/women-safety",
    tags=["Women Safety"],
)


def _compute_overview(profile: EmergencyProfile | None, contacts: List[TrustedContact]) -> WomenSafetyOverviewResponse:
    """Helper to construct authoritative overview and readiness status."""
    has_mobile = bool(profile and profile.emergency_mobile and profile.emergency_mobile.strip())
    consent = bool(profile and profile.location_sharing_consent)
    contacts_count = len(contacts)

    # profile_complete: true ONLY when:
    # 1. emergency profile exists with emergency_mobile
    # 2. location_sharing_consent is explicitly enabled
    # 3. at least 2 trusted contacts exist
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
    """
    Returns the authenticated user's emergency profile, trusted contacts list,
    and computed profile readiness status. Strictly tenant-isolated to the token owner.
    """
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
    """
    Creates or updates the authenticated user's emergency profile and location-sharing consent.
    Consent defaults to False and must be explicitly enabled by user action.
    """
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
    """
    Adds one trusted contact for the authenticated user.
    Enforces a strict maximum of 4 trusted contacts per user.
    """
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
    """
    Updates a trusted contact belonging to the authenticated user.
    Strictly checks ownership: returns 404 if contact does not exist or belongs to another user.
    """
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
    """
    Deletes a trusted contact belonging to the authenticated user.
    Strictly checks ownership: returns 404 if contact does not exist or belongs to another user.
    """
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


# ── WS-2: SOS Trigger & Emergency Events Endpoints ────────────────────────────

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
    """
    Creates an authenticated emergency event using validated browser GPS coordinates.
    Strictly enforces WS-1 profile completeness:
    - Emergency profile must exist with valid emergency_mobile
    - Location sharing consent must be explicitly granted (True)
    - At least 2 trusted contacts must exist

    Prevents duplicate active emergency sessions for the user.
    """
    # 1. WS-1 Profile Gate Verification
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

    # 2. Duplicate Active Event Check (One active emergency per user)
    existing_active = (
        db.query(EmergencyEvent)
        .filter(EmergencyEvent.user_id == current_user.id, EmergencyEvent.status == "ACTIVE")
        .first()
    )
    if existing_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active emergency session is already in progress for your account.",
        )

    # 3. Create Active Emergency Event
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
    return event


@router.get(
    "/emergency-events/active",
    response_model=ActiveEmergencyResponse,
    summary="Get authenticated user's current ACTIVE emergency event",
)
async def get_active_emergency_event(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the authenticated user's currently active emergency event if one exists.
    Allows session recovery after page refresh or navigation.
    """
    active_event = (
        db.query(EmergencyEvent)
        .filter(EmergencyEvent.user_id == current_user.id, EmergencyEvent.status == "ACTIVE")
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
    """
    Cancels an active emergency event belonging to the authenticated user.
    Updates status from ACTIVE to CANCELLED and records cancelled_at timestamp.
    Preserves the database record for historical/audit purposes (never deletes).
    Idempotent if already cancelled.
    """
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

    if event.status == "ACTIVE":
        event.status = "CANCELLED"
        event.cancelled_at = func.now()
        db.commit()
        db.refresh(event)

    return event
