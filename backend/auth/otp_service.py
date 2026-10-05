from __future__ import annotations

import os
import re
from hmac import compare_digest
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request

from auth_security import SlidingWindowLimiter, request_fingerprint, utc_now

from .jwt_service import issue_auth_tokens, decode_token
from .otp_generator import generate_otp
from .otp_store import (
    create_otp_session,
    create_user_session,
    delete_otp_session,
    get_active_otp_session,
    hash_otp,
    increment_otp_attempts,
    is_user_session_active,
    log_login_history,
    mark_otp_verified,
    revoke_otp_session,
    revoke_user_session,
)
from .sms_provider import build_sms_provider


PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "300"))
OTP_RESEND_DELAY_SECONDS = int(os.getenv("OTP_RESEND_DELAY_SECONDS", "30"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_REQUEST_LIMITER = SlidingWindowLimiter(window_seconds=60, max_requests=5)
OTP_VERIFY_LIMITER = SlidingWindowLimiter(window_seconds=60, max_requests=15)


def _validate_phone_number(phone_number: str) -> str:
    normalized = phone_number.strip()
    if not PHONE_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail="Phone number must be in E.164 format")
    return normalized


def _mask_phone(phone_number: str) -> str:
    if len(phone_number) <= 4:
        return phone_number
    return f"{phone_number[:3]}{'*' * max(4, len(phone_number) - 7)}{phone_number[-4:]}"


def _request_meta(request: Request) -> tuple[str, str, str]:
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    device_hash = request_fingerprint(request)
    return ip, user_agent, device_hash


def _session_expired(session: dict[str, Any]) -> bool:
    expires_at = datetime.fromisoformat(str(session["expires_at"]))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return utc_now() >= expires_at


def send_otp(phone_number: str, request: Request) -> dict[str, Any]:
    normalized_phone = _validate_phone_number(phone_number)
    ip, user_agent, _ = _request_meta(request)
    limiter_key = f"send:{normalized_phone}:{ip}"
    if not OTP_REQUEST_LIMITER.allow(limiter_key):
        raise HTTPException(status_code=429, detail="Too many OTP requests")

    existing = get_active_otp_session(normalized_phone)
    now = utc_now()
    if existing:
        resend_after = datetime.fromisoformat(str(existing["resend_after_at"]))
        if resend_after.tzinfo is None:
            resend_after = resend_after.replace(tzinfo=timezone.utc)
        if now < resend_after and not existing.get("revoked"):
            retry_after = max(1, int((resend_after - now).total_seconds()))
            raise HTTPException(
                status_code=429,
                detail={"message": "Resend allowed after cooldown", "retry_after_seconds": retry_after},
            )
        revoke_otp_session(str(existing["session_id"]))

    otp = generate_otp()
    otp_salt = os.urandom(16).hex()
    expires_at = (now + timedelta(seconds=OTP_TTL_SECONDS)).isoformat()
    resend_after_at = (now + timedelta(seconds=OTP_RESEND_DELAY_SECONDS)).isoformat()
    phone_hash = __import__("backend.auth.otp_store", fromlist=["hash_phone"]).hash_phone(normalized_phone)
    otp_hash_value = hash_otp(otp, otp_salt, phone_hash)
    session = create_otp_session(
        phone_number=normalized_phone,
        otp_hash=otp_hash_value,
        otp_salt=otp_salt,
        expires_at=expires_at,
        resend_after_at=resend_after_at,
        last_ip=ip,
        last_user_agent=user_agent,
    )

    sms = build_sms_provider().send(normalized_phone, f"Your LandSense OTP is {otp}. It expires in 5 minutes.")
    return {
        "message": "OTP sent",
        "phone_number": normalized_phone,
        "phone_number_masked": _mask_phone(normalized_phone),
        "resend_after_seconds": OTP_RESEND_DELAY_SECONDS,
        "expires_in_seconds": OTP_TTL_SECONDS,
        "session_id": session.get("session_id"),
        "delivery": {"status": sms.status, "provider": sms.provider},
    }


def verify_otp(phone_number: str, otp: str, request: Request) -> dict[str, Any]:
    normalized_phone = _validate_phone_number(phone_number)
    ip, user_agent, device_hash = _request_meta(request)
    session = get_active_otp_session(normalized_phone)
    if not session:
        raise HTTPException(status_code=404, detail="OTP session not found")

    limiter_key = f"verify:{session['session_id']}:{ip}"
    if not OTP_VERIFY_LIMITER.allow(limiter_key):
        raise HTTPException(status_code=429, detail="Too many verification attempts")

    if _session_expired(session):
        delete_otp_session(str(session["session_id"]))
        raise HTTPException(status_code=410, detail="OTP expired")
    if int(session.get("attempts", 0)) >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Maximum OTP attempts exceeded")

    expected_hash = str(session.get("otp_hash", ""))
    actual_hash = hash_otp(otp, str(session.get("otp_salt", "")), str(session.get("phone_hash", "")))
    if not compare_digest(expected_hash, actual_hash):
        updated = increment_otp_attempts(str(session["session_id"]))
        if updated and int(updated.get("attempts", 0)) >= OTP_MAX_ATTEMPTS:
            revoke_otp_session(str(session["session_id"]))
            raise HTTPException(status_code=429, detail="Maximum OTP attempts exceeded")
        raise HTTPException(status_code=400, detail="Invalid OTP")

    session = mark_otp_verified(str(session["session_id"])) or session
    verified_session_id = str(session["session_id"])
    token_bundle = issue_auth_tokens(
        subject=str(session["phone_number"]),
        phone_number=str(session["phone_number"]),
        device_hash=device_hash,
        session_id=verified_session_id,
    )
    create_user_session(
        session_id=verified_session_id,
        phone_number=str(session["phone_number"]),
        token_jti=str(token_bundle["access_jti"]),
        issued_at=utc_now().isoformat(),
        expires_at=(utc_now() + timedelta(minutes=int(token_bundle["access_expires_in_minutes"]))).isoformat(),
        last_ip=ip,
        last_user_agent=user_agent,
    )
    log_login_history(
        phone_number=str(session["phone_number"]),
        session_id=verified_session_id,
        status="verified",
        ip=ip,
        user_agent=user_agent,
    )
    delete_otp_session(verified_session_id)
    return {
        **token_bundle,
        "profile": {
            "phone_number": str(session["phone_number"]),
            "phone_number_masked": _mask_phone(str(session["phone_number"])),
            "verified": True,
            "session_id": verified_session_id,
        },
    }


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    return token.strip()


def authenticate_profile(authorization: str | None) -> dict[str, Any]:
    token = _extract_bearer_token(authorization)
    try:
        payload = decode_token(token, "access")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if not is_user_session_active(str(payload.get("jti", ""))):
        raise HTTPException(status_code=401, detail="Session is no longer active")
    return payload


def logout_session(payload: dict[str, Any]) -> dict[str, Any]:
    revoked = revoke_user_session(str(payload.get("jti", "")))
    return {"logged_out": revoked}
