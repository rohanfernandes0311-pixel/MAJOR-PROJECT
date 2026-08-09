from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from .otp_service import authenticate_profile


def get_current_auth_payload(authorization: str | None = Header(default=None)) -> dict:
    return authenticate_profile(authorization)


def require_auth(payload: dict = Depends(get_current_auth_payload)) -> dict:
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return payload
