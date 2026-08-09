"""Authentication package for the isolated LandSense gateway.

This module exposes a single `router` object that combines the legacy
OTP-based auth router and the newer Firebase exchange router so the
application can include a single auth router without further changes
to `backend_api.py`.
"""

from fastapi import APIRouter

from .auth_router import router as otp_router
from .router import router as firebase_router
from .middleware import JWTAuthMiddleware

router = APIRouter()
router.include_router(otp_router)
router.include_router(firebase_router)

# Register global JWT middleware on the main app so most APIs are protected.
try:
	# Import app from backend_api; app is created before importing this module in backend_api.py
	from backend_api import app  # type: ignore

	# Only add middleware if not already present
	has_middleware = any(type(m.middleware_class).__name__ == JWTAuthMiddleware.__name__ for m in getattr(app, "user_middleware", []))
	if not has_middleware:
		app.add_middleware(JWTAuthMiddleware)
except Exception:
	# If import fails (for tooling or test contexts) don't crash on import
	pass
