"""
NAVISCAPE Firebase Integration Layer
Provides Firebase Admin SDK initialization, Firestore client provider,
and Firebase Authentication token verification.
"""

import os
import json
import logging
from typing import Optional, Dict, Any

import firebase_admin
from firebase_admin import credentials, firestore, auth

from .config import settings

logger = logging.getLogger(__name__)

_firebase_app: Optional[firebase_admin.App] = None
_firestore_db: Optional[firestore.firestore.Client] = None


def _resolve_service_account_path(path: Optional[str]) -> Optional[str]:
    """
    Resolve service account file path supporting absolute paths,
    paths relative to cwd, and paths relative to backend directory.
    """
    if not path:
        return None
    # 1. Direct path check (absolute or relative to current working directory)
    if os.path.exists(path):
        return os.path.abspath(path)
    # 2. Relative to backend directory
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_relative = os.path.join(backend_dir, path)
    if os.path.exists(backend_relative):
        return os.path.abspath(backend_relative)
    # 3. Default serviceAccountKey.json in backend directory
    default_key = os.path.join(backend_dir, "serviceAccountKey.json")
    if os.path.exists(default_key):
        return os.path.abspath(default_key)
    return None


def get_firebase_app() -> Optional[firebase_admin.App]:
    """
    Initialize or return the singleton Firebase Admin App instance.
    Supports:
    1. Service Account JSON file path (FIREBASE_SERVICE_ACCOUNT_PATH)
    2. Raw Service Account JSON string (FIREBASE_SERVICE_ACCOUNT_JSON)
    3. Project ID / Google Application Default Credentials (ADC)
    4. Default dummy project initialization for graceful fallback.
    """
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    # Check if Firebase is already initialized
    if firebase_admin._apps:
        _firebase_app = firebase_admin.get_app()
        return _firebase_app

    service_account_path = _resolve_service_account_path(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
    service_account_json = settings.FIREBASE_SERVICE_ACCOUNT_JSON
    project_id = settings.FIREBASE_PROJECT_ID

    try:
        if service_account_path and os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info(f"Initialized Firebase Admin with service account file: {service_account_path}")
        elif service_account_json:
            cred_dict = json.loads(service_account_json)
            cred = credentials.Certificate(cred_dict)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Initialized Firebase Admin with service account JSON string")
        elif project_id:
            _firebase_app = firebase_admin.initialize_app(options={"projectId": project_id})
            logger.info(f"Initialized Firebase Admin with Project ID: {project_id}")
        else:
            # Fallback initialization using project id if available or mock
            _firebase_app = firebase_admin.initialize_app(options={"projectId": "naviscape-default"})
            logger.info("Initialized Firebase Admin with default project context")
    except Exception as e:
        logger.warning(f"Firebase Admin initialization note: {e}")
        try:
            _firebase_app = firebase_admin.get_app()
        except Exception:
            _firebase_app = None

    return _firebase_app


def get_firestore_db() -> Optional[firestore.firestore.Client]:
    """
    Get the Firestore database client instance.
    """
    global _firestore_db
    if _firestore_db is not None:
        return _firestore_db

    app = get_firebase_app()
    if app is not None:
        try:
            _firestore_db = firestore.client(app=app)
            return _firestore_db
        except Exception as e:
            logger.warning(f"Firestore client initialization note: {e}")
            return None
    return None


def verify_firebase_id_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Firebase Auth ID token from the frontend Authorization header.
    Returns decoded token dictionary or None on failure.
    """
    if not id_token:
        return None

    # Fast-path: Check unverified JWT header/claims to distinguish Firebase RS256 token from local HS256 JWT
    try:
        from jose import jwt as jose_jwt
        unverified_claims = jose_jwt.get_unverified_claims(id_token)
        iss = unverified_claims.get("iss", "")
        # Firebase ID tokens have issuer starting with https://securetoken.google.com/
        if not iss.startswith("https://securetoken.google.com/"):
            return None
    except Exception:
        # If token can't be parsed, let Firebase auth verify or reject
        pass

    app = get_firebase_app()
    if not app:
        return None

    try:
        decoded_token = auth.verify_id_token(id_token, app=app)
        return decoded_token
    except Exception as e:
        logger.debug(f"Firebase ID token verification failed: {e}")
        return None
