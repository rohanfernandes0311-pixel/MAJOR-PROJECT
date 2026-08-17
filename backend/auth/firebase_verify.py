from __future__ import annotations

from pathlib import Path
from datetime import timedelta
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials

from auth_security import new_jti, utc_now
from backend.auth import jwt_service
from backend.auth import otp_store
from local_store import get_user, upsert_user
from backend.auth.otp_store import hash_phone


BASE_DIR = Path(__file__).resolve().parents[2]
FIREBASE_SERVICE_ACCOUNT_PATH = BASE_DIR / "config" / "firebase-service-account.json"


def _init_firebase() -> None:
    if firebase_admin._apps:
        return
    if not FIREBASE_SERVICE_ACCOUNT_PATH.exists():
        raise ValueError(f"Firebase service account file not found at {FIREBASE_SERVICE_ACCOUNT_PATH}")
    cred = credentials.Certificate(str(FIREBASE_SERVICE_ACCOUNT_PATH))
    firebase_admin.initialize_app(cred)


def verify_firebase_id_token(id_token: str) -> dict[str, Any]:
    """Verify the Firebase ID token and return decoded token payload.

    Raises firebase_admin.exceptions.FirebaseError on failure.
    """
    if not id_token or not id_token.strip():
        raise ValueError("Missing Firebase ID token")
    _init_firebase()
    return firebase_auth.verify_id_token(id_token.strip())


def exchange_firebase_token(id_token: str, device_hash: str | None = None, last_ip: str | None = None, user_agent: str | None = None) -> dict[str, Any]:
    """Verify Firebase ID token, upsert user, issue JWTs and persist session.

    Returns a dict with access_token, refresh_token, expires_in, profile.
    """
    decoded = verify_firebase_id_token(id_token)
    uid = decoded.get("uid")
    phone_number = decoded.get("phone_number") or decoded.get("phone")
    name = decoded.get("name") or ""

    if not uid or not phone_number:
        raise ValueError("Firebase token missing uid or phone_number")

    # Roles are assigned only from the persisted server-side user record.  Do
    # not accept a role from the Firebase token or client request: new users
    # must begin as Citizens and existing users retain their stored role.
    existing = get_user(uid)

    # Create or update the user without changing any stored role.
    phone_hash = hash_phone(phone_number)
    device_hash = device_hash or ""
    upsert_user(uid=uid, phone_number=phone_number, phone_hash=phone_hash, name=name or None, device_hash=device_hash)

    role = jwt_service.normalize_role(existing.get("role") if existing else None)

    session_id = new_jti()
    token_bundle = jwt_service.issue_auth_tokens(
        subject=uid,
        phone_number=phone_number,
        device_hash=device_hash,
        session_id=session_id,
        role=role,
    )

    # Persist session in user_sessions table
    issued_at = utc_now()
    access_expires_minutes = int(token_bundle.get("access_expires_in_minutes", 15))
    expires_at = (issued_at + timedelta(minutes=access_expires_minutes)).isoformat()
    otp_store.create_user_session(
        session_id=session_id,
        phone_number=phone_number,
        token_jti=str(token_bundle.get("access_jti")),
        issued_at=issued_at.isoformat(),
        expires_at=expires_at,
        last_ip=last_ip or "",
        last_user_agent=user_agent or "",
    )

    otp_store.log_login_history(
        phone_number=phone_number,
        session_id=session_id,
        status="firebase_verified",
        ip=last_ip or "",
        user_agent=user_agent or "",
    )

    return {
        "token_type": token_bundle.get("token_type"),
        "access_token": token_bundle.get("access_token"),
        "refresh_token": token_bundle.get("refresh_token"),
        "expires_in": access_expires_minutes * 60,
        "profile": {"uid": uid, "phone_number": phone_number, "name": name, "role": role},
    }
