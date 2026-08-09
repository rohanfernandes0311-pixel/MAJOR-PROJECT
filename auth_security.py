from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Request


ACCESS_TOKEN_TTL_MIN = int(os.getenv("ACCESS_TOKEN_TTL_MIN", "15"))
REFRESH_TOKEN_TTL_DAYS = int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "7"))
JWT_SECRET = os.getenv("JWT_SECRET", "change-this-in-production")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")
PHONE_HASH_SALT = os.getenv("PHONE_HASH_SALT", "landsense-default-salt")


class SlidingWindowLimiter:
    """Simple in-memory sliding-window limiter.

    Use Redis for distributed production deployments.
    """

    def __init__(self, window_seconds: int, max_requests: int) -> None:
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        bucket = self._requests[key]
        while bucket and (now - bucket[0]) > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_phone(phone_number: str) -> str:
    data = f"{PHONE_HASH_SALT}:{phone_number.strip()}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_device_fingerprint(device_fingerprint: str) -> str:
    normalized = device_fingerprint.strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def request_fingerprint(request: Request, device_fingerprint: str | None = None) -> str:
    user_agent = request.headers.get("user-agent", "unknown")
    ip = request.client.host if request.client else "unknown"
    source = device_fingerprint or f"{user_agent}|{ip}"
    return hash_device_fingerprint(source)


def create_access_token(uid: str, phone_number: str, device_hash: str) -> str:
    now = utc_now()
    payload = {
        "sub": uid,
        "phone": phone_number,
        "device": device_hash,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_TTL_MIN)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def create_refresh_token(uid: str, phone_number: str, device_hash: str, jti: str) -> str:
    now = utc_now()
    payload = {
        "sub": uid,
        "phone": phone_number,
        "device": device_hash,
        "type": "refresh",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    token_type = payload.get("type")
    if token_type != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


def secure_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def new_jti() -> str:
    return secrets.token_urlsafe(24)
