from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

import jwt

from auth_security import utc_now, new_jti


JWT_SECRET = os.getenv("JWT_SECRET", "change-this-in-production")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")
ACCESS_TOKEN_TTL_MIN = int(os.getenv("ACCESS_TOKEN_TTL_MIN", "15"))
REFRESH_TOKEN_TTL_DAYS = int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "7"))


def issue_auth_tokens(*, subject: str, phone_number: str, device_hash: str, session_id: str, role: str | None = None) -> dict[str, str | int]:
    now = utc_now()
    access_jti = new_jti()
    refresh_jti = new_jti()
    role = role or "Citizen"

    access_payload = {
        "sub": subject,
        "phone": phone_number,
        "role": role,
        "device": device_hash,
        "sid": session_id,
        "jti": access_jti,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_TTL_MIN)).timestamp()),
    }
    refresh_payload = {
        "sub": subject,
        "phone": phone_number,
        "role": role,
        "device": device_hash,
        "sid": session_id,
        "jti": refresh_jti,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)).timestamp()),
    }

    return {
        "token_type": "bearer",
        "access_token": jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGO),
        "refresh_token": jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGO),
        "access_expires_in_minutes": ACCESS_TOKEN_TTL_MIN,
        "refresh_expires_in_days": REFRESH_TOKEN_TTL_DAYS,
        "access_jti": access_jti,
        "refresh_jti": refresh_jti,
    }


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid token") from exc

    if payload.get("type") != expected_type:
        raise ValueError("Invalid token type")
    return payload
