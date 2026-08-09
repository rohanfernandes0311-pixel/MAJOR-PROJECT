"""Authentication package for the isolated LandSense gateway.

This module exposes a single `router` object that combines the legacy
OTP-based auth router and the newer Firebase exchange router so the
application can include a single auth router without further changes
to `backend_api.py`.
"""

from fastapi import APIRouter

from .auth_router import router as otp_router
from .router import router as firebase_router

router = APIRouter()
router.include_router(otp_router)
router.include_router(firebase_router)
