"""
NAVISCAPE Firestore Repository Layer
Clean, centralized Firestore Data Access Layer for all 11 collections:
1. users
2. emergency_profiles
3. trusted_contacts
4. emergency_events
5. route_history
6. road_hazards
7. police_stations
8. hospital_facilities
9. accident_data
10. traffic_data
11. traffic_hourly
"""

import math
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from ..firebase import get_firestore_db

logger = logging.getLogger(__name__)


def _to_iso(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, datetime):
        return val.isoformat()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class FirestoreRepository:
    """
    Centralized Firestore Repository handling queries, reads, writes, and batching.
    """

    def __init__(self):
        self._db = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_firestore_db()
        return self._db

    # ─────────────────────────────────────────────────────────────────────────
    # 1. USERS (users/{firebase_uid})
    # ─────────────────────────────────────────────────────────────────────────

    def get_user_by_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        if not self.db or not uid:
            return None
        doc = self.db.collection("users").document(str(uid)).get()
        if doc.exists:
            data = doc.to_dict()
            data["id"] = data.get("sqlite_legacy_id") or uid
            data["uid"] = uid
            return data
        return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        if not self.db or not email:
            return None
        normalized = email.strip().lower()
        docs = (
            self.db.collection("users")
            .where("email", "==", normalized)
            .limit(1)
            .get()
        )
        for d in docs:
            data = d.to_dict()
            data["uid"] = d.id
            data["id"] = data.get("sqlite_legacy_id") or d.id
            return data
        return None

    def get_user_by_legacy_id(self, legacy_id: int) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None
        docs = (
            self.db.collection("users")
            .where("sqlite_legacy_id", "==", legacy_id)
            .limit(1)
            .get()
        )
        for d in docs:
            data = d.to_dict()
            data["uid"] = d.id
            data["id"] = legacy_id
            return data
        return None

    def create_or_update_user(self, uid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.db:
            raise RuntimeError("Firestore DB client not available")

        doc_ref = self.db.collection("users").document(str(uid))
        existing = doc_ref.get()

        now_iso = datetime.now(timezone.utc).isoformat()
        user_dict = {
            "email": (data.get("email") or "").strip().lower(),
            "full_name": data.get("full_name") or data.get("name") or "",
            "username": data.get("username") or (data.get("email") or "").split("@")[0],
            "email_verified": data.get("email_verified", True),
            "is_active": data.get("is_active", True),
            "is_admin": data.get("is_admin", False),
            "sqlite_legacy_id": data.get("sqlite_legacy_id"),
            "updated_at": now_iso,
        }

        if not existing.exists:
            user_dict["created_at"] = data.get("created_at") or now_iso

        doc_ref.set(user_dict, merge=True)
        user_dict["uid"] = str(uid)
        user_dict["id"] = user_dict.get("sqlite_legacy_id") or str(uid)
        return user_dict

    def update_user(self, uid: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None
        doc_ref = self.db.collection("users").document(str(uid))
        if not doc_ref.get().exists:
            return None
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        doc_ref.update(updates)
        return self.get_user_by_uid(uid)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. EMERGENCY PROFILES (emergency_profiles/{user_id})
    # ─────────────────────────────────────────────────────────────────────────

    def get_emergency_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None
        try:
            doc = self.db.collection("emergency_profiles").document(str(user_id)).get(timeout=2.0)
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            logger.warning(f"Firestore get_emergency_profile note: {e}")
            return None
        return None


    def create_or_update_emergency_profile(
        self, user_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not self.db:
            raise RuntimeError("Firestore DB client not available")

        doc_ref = self.db.collection("emergency_profiles").document(str(user_id))
        now_iso = datetime.now(timezone.utc).isoformat()

        payload = {
            "user_id": str(user_id),
            "sqlite_legacy_id": data.get("sqlite_legacy_id"),
            "emergency_mobile": data.get("emergency_mobile"),
            "emergency_email": data.get("emergency_email"),
            "location_sharing_consent": bool(data.get("location_sharing_consent", False)),
            "updated_at": now_iso,
        }
        try:
            payload["created_at"] = data.get("created_at") or now_iso
            doc_ref.set(payload, merge=True, timeout=2.0)
            return payload
        except Exception as e:
            logger.warning(f"Firestore emergency profile update note: {e}")
            return payload



    def delete_emergency_profile(self, user_id: str) -> bool:
        if not self.db:
            return False
        doc_ref = self.db.collection("emergency_profiles").document(str(user_id))
        if doc_ref.get().exists:
            doc_ref.delete()
            return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # 3. TRUSTED CONTACTS (trusted_contacts/{contact_id})
    # ─────────────────────────────────────────────────────────────────────────

    def get_trusted_contacts(self, user_id: str) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        contacts = []

        # Query by string user_id
        docs = (
            self.db.collection("trusted_contacts")
            .where("user_id", "==", str(user_id))
            .get()
        )
        for d in docs:
            item = d.to_dict()
            item["doc_id"] = d.id
            contacts.append(item)

        # Fallback query for legacy int user_id if string query was empty
        if not contacts and str(user_id).isdigit():
            docs = (
                self.db.collection("trusted_contacts")
                .where("sqlite_legacy_user_id", "==", int(user_id))
                .get()
            )
            for d in docs:
                item = d.to_dict()
                item["doc_id"] = d.id
                contacts.append(item)

        # Sort by id or created_at
        contacts.sort(key=lambda x: x.get("id") or x.get("created_at") or "")
        return contacts

    def create_trusted_contact(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.db:
            raise RuntimeError("Firestore DB client not available")

        current_count = len(self.get_trusted_contacts(user_id))
        if current_count >= 4:
            raise ValueError("Maximum of 4 trusted contacts allowed per user.")

        now_iso = datetime.now(timezone.utc).isoformat()
        doc_ref = self.db.collection("trusted_contacts").document()

        contact_id = data.get("id") or doc_ref.id
        payload = {
            "id": contact_id,
            "user_id": str(user_id),
            "sqlite_legacy_user_id": data.get("sqlite_legacy_user_id"),
            "contact_name": data.get("contact_name") or "",
            "relationship": data.get("relationship") or "",
            "mobile_number": data.get("mobile_number") or "",
            "email": data.get("email"),
            "whatsapp_number": data.get("whatsapp_number"),
            "whatsapp_alert_consent": bool(data.get("whatsapp_alert_consent", False)),
            "created_at": data.get("created_at") or now_iso,
            "updated_at": now_iso,
        }

        try:
            doc_ref.set(payload, timeout=2.0)
        except Exception as e:
            logger.warning(f"Firestore trusted contact write note: {e}")
        payload["doc_id"] = doc_ref.id
        return payload


    def update_trusted_contact(
        self, contact_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None

        # Find document by doc_id or id field
        doc_ref = self.db.collection("trusted_contacts").document(str(contact_id))
        if not doc_ref.get().exists:
            docs = (
                self.db.collection("trusted_contacts")
                .where("id", "==", contact_id)
                .limit(1)
                .get()
            )
            if not docs and str(contact_id).isdigit():
                docs = (
                    self.db.collection("trusted_contacts")
                    .where("id", "==", int(contact_id))
                    .limit(1)
                    .get()
                )
            if docs:
                doc_ref = docs[0].reference

        if not doc_ref.get().exists:
            return None

        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        doc_ref.update(data)
        res = doc_ref.get().to_dict()
        res["doc_id"] = doc_ref.id
        return res

    def delete_trusted_contact(self, contact_id: str, user_id: str = None) -> bool:
        if not self.db:
            return False

        doc_ref = self.db.collection("trusted_contacts").document(str(contact_id))
        if doc_ref.get().exists:
            doc_ref.delete()
            return True

        # Query by id field
        query = self.db.collection("trusted_contacts").where("id", "==", contact_id)
        if str(contact_id).isdigit():
            docs = (
                self.db.collection("trusted_contacts")
                .where("id", "==", int(contact_id))
                .get()
            )
        else:
            docs = query.get()

        for d in docs:
            if user_id is None or d.to_dict().get("user_id") == str(user_id):
                d.reference.delete()
                return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # 4. EMERGENCY EVENTS / SOS (emergency_events/{event_id})
    # ─────────────────────────────────────────────────────────────────────────

    def create_emergency_event(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.db:
            raise RuntimeError("Firestore DB client not available")

        now_iso = datetime.now(timezone.utc).isoformat()
        doc_ref = self.db.collection("emergency_events").document()

        event_id = data.get("id") or doc_ref.id
        payload = {
            "id": event_id,
            "user_id": str(user_id),
            "sqlite_legacy_user_id": data.get("sqlite_legacy_user_id"),
            "status": data.get("status", "ACTIVE"),
            "triggered_at": _to_iso(data.get("triggered_at")) or now_iso,
            "cancelled_at": _to_iso(data.get("cancelled_at")),
            "latitude": float(data["latitude"]),
            "longitude": float(data["longitude"]),
            "location_accuracy_m": (
                float(data["location_accuracy_m"])
                if data.get("location_accuracy_m") is not None
                else None
            ),
            "created_at": _to_iso(data.get("created_at")) or now_iso,
            "updated_at": now_iso,
        }

        doc_ref.set(payload)
        payload["doc_id"] = doc_ref.id
        return payload

    def get_emergency_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None
        doc = self.db.collection("emergency_events").document(str(event_id)).get()
        if doc.exists:
            item = doc.to_dict()
            item["doc_id"] = doc.id
            return item

        docs = (
            self.db.collection("emergency_events")
            .where("id", "==", event_id)
            .limit(1)
            .get()
        )
        if not docs and str(event_id).isdigit():
            docs = (
                self.db.collection("emergency_events")
                .where("id", "==", int(event_id))
                .limit(1)
                .get()
            )
        for d in docs:
            item = d.to_dict()
            item["doc_id"] = d.id
            return item
        return None

    def get_active_emergency_event(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None
        docs = (
            self.db.collection("emergency_events")
            .where("user_id", "==", str(user_id))
            .where("status", "==", "ACTIVE")
            .limit(1)
            .get()
        )
        for d in docs:
            item = d.to_dict()
            item["doc_id"] = d.id
            return item
        return None

    def update_emergency_event(
        self, event_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None

        event = self.get_emergency_event(event_id)
        if not event:
            return None

        doc_id = event["doc_id"]
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.db.collection("emergency_events").document(doc_id).update(updates)
        return self.get_emergency_event(event_id)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. ROUTE HISTORY (route_history/{history_id})
    # ─────────────────────────────────────────────────────────────────────────

    def add_route_history(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.db:
            raise RuntimeError("Firestore DB client not available")

        now_iso = datetime.now(timezone.utc).isoformat()
        doc_ref = self.db.collection("route_history").document()

        history_id = data.get("id") or doc_ref.id
        payload = {
            "id": history_id,
            "user_id": str(user_id),
            "sqlite_legacy_user_id": data.get("sqlite_legacy_user_id"),
            "source_lat": float(data["source_lat"]),
            "source_lng": float(data["source_lng"]),
            "dest_lat": float(data["dest_lat"]),
            "dest_lng": float(data["dest_lng"]),
            "source_name": data.get("source_name"),
            "dest_name": data.get("dest_name"),
            "distance_km": float(data["distance_km"]) if data.get("distance_km") is not None else None,
            "duration_min": float(data["duration_min"]) if data.get("duration_min") is not None else None,
            "safety_score": float(data["safety_score"]) if data.get("safety_score") is not None else None,
            "route_type": data.get("route_type", "balanced"),
            "created_at": _to_iso(data.get("created_at")) or now_iso,
        }

        doc_ref.set(payload)
        payload["doc_id"] = doc_ref.id
        return payload

    def get_route_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        routes = []

        docs = (
            self.db.collection("route_history")
            .where("user_id", "==", str(user_id))
            .limit(limit)
            .get()
        )
        for d in docs:
            item = d.to_dict()
            item["doc_id"] = d.id
            routes.append(item)

        if not routes and str(user_id).isdigit():
            docs = (
                self.db.collection("route_history")
                .where("sqlite_legacy_user_id", "==", int(user_id))
                .limit(limit)
                .get()
            )
            for d in docs:
                item = d.to_dict()
                item["doc_id"] = d.id
                routes.append(item)

        routes.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return routes

    # ─────────────────────────────────────────────────────────────────────────
    # 6. ROAD HAZARDS (road_hazards/{hazard_id})
    # ─────────────────────────────────────────────────────────────────────────

    def create_road_hazard(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.db:
            raise RuntimeError("Firestore DB client not available")

        now_iso = datetime.now(timezone.utc).isoformat()
        doc_ref = self.db.collection("road_hazards").document()

        hazard_id = data.get("id") or doc_ref.id
        payload = {
            "id": hazard_id,
            "user_id": str(user_id),
            "sqlite_legacy_user_id": data.get("sqlite_legacy_user_id"),
            "hazard_type": data.get("hazard_type") or "Pothole",
            "severity": data.get("severity") or "Medium",
            "latitude": float(data["latitude"]),
            "longitude": float(data["longitude"]),
            "description": data.get("description"),
            "status": data.get("status", "Active"),
            "created_at": _to_iso(data.get("created_at")) or now_iso,
        }

        try:
            doc_ref.set(payload, timeout=2.0)
        except Exception as e:
            logger.warning(f"Firestore hazard write note: {e}")
        payload["doc_id"] = doc_ref.id
        return payload


    def get_road_hazards(self, status: str = None, limit: int = 200) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        query = self.db.collection("road_hazards")
        if status:
            query = query.where("status", "==", status)
        docs = query.limit(limit).get()
        hazards = []
        for d in docs:
            item = d.to_dict()
            item["doc_id"] = d.id
            hazards.append(item)
        return hazards

    def update_road_hazard_status(self, hazard_id: str, status: str) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None
        doc_ref = self.db.collection("road_hazards").document(str(hazard_id))
        if not doc_ref.get().exists:
            docs = (
                self.db.collection("road_hazards")
                .where("id", "==", hazard_id)
                .limit(1)
                .get()
            )
            if not docs and str(hazard_id).isdigit():
                docs = (
                    self.db.collection("road_hazards")
                    .where("id", "==", int(hazard_id))
                    .limit(1)
                    .get()
                )
            if docs:
                doc_ref = docs[0].reference

        if not doc_ref.get().exists:
            return None

        doc_ref.update({"status": status})
        res = doc_ref.get().to_dict()
        res["doc_id"] = doc_ref.id
        return res

    # ─────────────────────────────────────────────────────────────────────────
    # 7. POLICE STATIONS (police_stations/{station_id})
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_police_stations(self) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        docs = self.db.collection("police_stations").get()
        stations = []
        for d in docs:
            stations.append(d.to_dict())
        return stations

    def get_police_stations_near(
        self, lat: float, lng: float, max_dist_km: float = 50.0
    ) -> List[Dict[str, Any]]:
        stations = self.get_all_police_stations()
        results = []
        for s in stations:
            s_lat = s.get("latitude")
            s_lng = s.get("longitude")
            if s_lat is not None and s_lng is not None:
                dist = _haversine_km(lat, lng, float(s_lat), float(s_lng))
                if dist <= max_dist_km:
                    item = dict(s)
                    item["distance_km"] = round(dist, 2)
                    results.append(item)
        results.sort(key=lambda x: x["distance_km"])
        return results

    # ─────────────────────────────────────────────────────────────────────────
    # 8. HOSPITAL FACILITIES (hospital_facilities/{hospital_id})
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_hospitals(self, map_ready_only: bool = True) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        docs = self.db.collection("hospital_facilities").get()
        hospitals = []
        for d in docs:
            item = d.to_dict()
            if map_ready_only:
                h_lat = item.get("latitude")
                h_lng = item.get("longitude")
                if h_lat is None or h_lng is None:
                    continue
                # Karnataka bounding box check
                if not (11.0 <= float(h_lat) <= 19.0 and 73.5 <= float(h_lng) <= 79.0):
                    continue
            hospitals.append(item)
        return hospitals

    def get_hospitals_near(
        self, lat: float, lng: float, radius_km: float = 25.0
    ) -> List[Dict[str, Any]]:
        hospitals = self.get_all_hospitals(map_ready_only=True)
        results = []
        for h in hospitals:
            dist = _haversine_km(lat, lng, float(h["latitude"]), float(h["longitude"]))
            if dist <= radius_km:
                item = dict(h)
                item["distance_km"] = round(dist, 2)
                results.append(item)
        results.sort(key=lambda x: x["distance_km"])
        return results

    # ─────────────────────────────────────────────────────────────────────────
    # 9. ACCIDENT DATA (accident_data/{accident_id}) — 95k dataset pagination
    # ─────────────────────────────────────────────────────────────────────────

    def get_accident_count(self) -> int:
        if not self.db:
            return 0
        try:
            aggregate_query = self.db.collection("accident_data").count()
            results = aggregate_query.get()
            return results[0][0].value
        except Exception:
            # Fallback if aggregation count is not available in SDK version
            return 0


    def get_accidents_paginated(
        self, limit: int = 100, start_after_doc_id: str = None
    ) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        query = self.db.collection("accident_data").limit(limit)
        if start_after_doc_id:
            start_doc = self.db.collection("accident_data").document(start_after_doc_id).get()
            if start_doc.exists:
                query = query.start_after(start_doc)
        docs = query.get()
        return [d.to_dict() for d in docs]

    def get_accidents_in_bounds(
        self, min_lat: float, max_lat: float, min_lng: float, max_lng: float, limit: int = 5000
    ) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        # Firestore composite range query on latitude
        docs = (
            self.db.collection("accident_data")
            .where("latitude", ">=", min_lat)
            .where("latitude", "<=", max_lat)
            .limit(limit * 2)
            .get()
        )
        results = []
        for d in docs:
            item = d.to_dict()
            lng = item.get("longitude")
            if lng is not None and min_lng <= float(lng) <= max_lng:
                results.append(item)
                if len(results) >= limit:
                    break
        return results

    def get_accidents_sample(self, limit: int = 2000) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        docs = self.db.collection("accident_data").limit(limit).get()
        return [d.to_dict() for d in docs]

    # ─────────────────────────────────────────────────────────────────────────
    # 10 & 11. TRAFFIC DATA & TRAFFIC HOURLY
    # ─────────────────────────────────────────────────────────────────────────

    def get_traffic_data(
        self, junction_id: int = None, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        query = self.db.collection("traffic_data")
        if junction_id is not None:
            query = query.where("junction_id", "==", int(junction_id))
        docs = query.limit(limit).get()
        return [d.to_dict() for d in docs]

    def get_traffic_hourly(
        self, junction_id: int = None, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        query = self.db.collection("traffic_hourly")
        if junction_id is not None:
            query = query.where("junction_id", "==", int(junction_id))
        docs = query.limit(limit).get()
        return [d.to_dict() for d in docs]


# Global singleton repository instance
firestore_repo = FirestoreRepository()
