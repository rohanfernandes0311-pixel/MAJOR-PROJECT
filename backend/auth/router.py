from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from firebase_admin import exceptions as firebase_exceptions
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from auth_security import new_jti, request_fingerprint, utc_now
from backend.auth.firebase_verify import exchange_firebase_token
from backend.auth import jwt_service
from backend.auth.middleware import RequireAuthMiddleware
from backend.auth.otp_store import create_user_session, get_user_session_by_jti, revoke_user_session
from local_store import get_user
from datetime import timedelta


router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)


class FirebaseExchangeRequest(BaseModel):
    id_token: str = Field(..., min_length=100)
    device_hash: str | None = None


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


@router.post("/auth/firebase/exchange")
def post_firebase_exchange(req: FirebaseExchangeRequest, request: Request) -> dict[str, Any]:
    """Exchange a Firebase ID token for local JWTs."""
    try:
        device = req.device_hash or request_fingerprint(request)
        return exchange_firebase_token(
            req.id_token,
            device_hash=device,
            last_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", ""),
        )
    except (ValueError, firebase_exceptions.FirebaseError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Firebase exchange failed because database access was unavailable")
        raise HTTPException(
            status_code=503,
            detail="Unable to complete sign-in right now. Please try again.",
        ) from exc


@router.post("/auth/refresh")
def post_refresh(req: TokenRefreshRequest, request: Request) -> dict[str, Any]:
    try:
        payload = jwt_service.decode_token(req.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    sub = str(payload.get("sub", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    device = str(payload.get("device", "")).strip() or request_fingerprint(request)
    # Re-read the role from trusted persisted state.  This prevents a stale
    # refresh token from preserving a role after a server-side role change.
    user = get_user(sub) if sub else None
    role = jwt_service.normalize_role(user.get("role") if user else None)
    if not sub or not phone:
        raise HTTPException(status_code=400, detail="Malformed token payload")

    session_id = new_jti()
    new_tokens = jwt_service.issue_auth_tokens(
        subject=sub,
        phone_number=phone,
        device_hash=device,
        session_id=session_id,
        role=role,
    )

    issued_at = utc_now()
    access_expires_minutes = int(new_tokens.get("access_expires_in_minutes", 15))
    create_user_session(
        session_id=session_id,
        phone_number=phone,
        token_jti=str(new_tokens.get("access_jti")),
        issued_at=issued_at.isoformat(),
        expires_at=(issued_at + timedelta(minutes=access_expires_minutes)).isoformat(),
        last_ip=request.client.host if request.client else "",
        last_user_agent=request.headers.get("user-agent", ""),
    )

    return {
        "token_type": new_tokens.get("token_type"),
        "access_token": new_tokens.get("access_token"),
        "refresh_token": new_tokens.get("refresh_token"),
        "expires_in": access_expires_minutes * 60,
    }


@router.post("/auth/logout")
def post_logout(payload: dict = Depends(RequireAuthMiddleware())) -> dict[str, Any]:
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=400, detail="Invalid session")
    revoked = revoke_user_session(jti)
    return {"revoked": revoked}


@router.get("/auth/me")
def get_me(payload: dict = Depends(RequireAuthMiddleware())) -> dict[str, Any]:
    jti = payload.get("jti")
    session = get_user_session_by_jti(jti) if jti else None
    sub = payload.get("sub")
    user = get_user(str(sub)) if sub else None
    role = jwt_service.normalize_role(payload.get("role"))
    if user and user.get("role"):
        role = jwt_service.normalize_role(user.get("role"))

    phone = str(payload.get("phone", ""))
    profile = {
        "uid": sub,
        "phone": phone,
        "phone_masked": f"{phone[:3]}******{phone[-4:]}" if len(phone) >= 7 else phone,
        "session_id": payload.get("sid"),
        "role": role,
    }
    return {"authenticated": True, "profile": profile, "session": session}
