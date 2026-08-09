from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from .dependencies import get_current_auth_payload, require_auth
from .otp_service import logout_session, send_otp, verify_otp


router = APIRouter(tags=["auth"])


class SendOtpRequest(BaseModel):
    phone_number: str = Field(..., min_length=8)


class VerifyOtpRequest(BaseModel):
    phone_number: str = Field(..., min_length=8)
    otp: str = Field(..., min_length=6, max_length=6)


@router.post("/send-otp")
def post_send_otp(req: SendOtpRequest, request: Request) -> dict[str, Any]:
    return send_otp(req.phone_number, request)


@router.post("/verify-otp")
def post_verify_otp(req: VerifyOtpRequest, request: Request) -> dict[str, Any]:
    return verify_otp(req.phone_number, req.otp, request)


@router.post("/logout")
def post_logout(payload: dict = Depends(require_auth)) -> dict[str, Any]:
    return logout_session(payload)


@router.get("/profile")
def get_profile(payload: dict = Depends(get_current_auth_payload)) -> dict[str, Any]:
    return {
        "profile": {
            "phone_number": payload.get("phone"),
            "phone_number_masked": f"{str(payload.get('phone', ''))[:3]}******{str(payload.get('phone', ''))[-4:]}",
        },
        "authenticated": True,
    }
