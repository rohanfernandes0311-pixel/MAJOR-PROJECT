from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.auth import jwt_service
from backend.auth.otp_store import is_user_session_active


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    return parts[1]


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = _extract_bearer_token(authorization)
    try:
        payload = jwt_service.decode_token(token, expected_type="access")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    jti = payload.get("jti")
    if not jti or not is_user_session_active(jti):
        raise HTTPException(status_code=401, detail="Session not active")
    return payload


def require_admin(payload: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Require an authenticated JWT issued to an Admin role.

    The role is deliberately taken from the signed access-token payload; callers
    cannot supply a role through a request header or body.
    """
    if str(payload.get("role", "")).strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return payload


class RequireAuthMiddleware:
    """ASGI-style middleware-like dependency provider.

    Use as: `payload: dict = Depends(RequireAuthMiddleware())`
    """

    def __call__(self, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        return get_current_user(authorization)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Global middleware to protect most API endpoints with JWT access tokens.

    Exempt paths (login, otp flows, auth exchange and refresh, static assets, docs) are allowed.
    """

    EXEMPT_PATH_PREFIXES = (
        "/login",
        "/otp",
        "/auth/firebase/exchange",
        "/auth/refresh",
        "/send-otp",
        "/verify-otp",
        "/public",
        "/assets",
        "/icons/",
        "/images/",
        "/frontend/assets",
        "/dist",
        "/favicon.ico",
        "/manifest.json",
        "/sw.js",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/_next",
    )
    EXEMPT_PATHS = {
        "/",
        "/admin",
        "/admin/simulation",
        "/admin/simulation/demo",
        "/frontend/admin/simulation",
        "/frontend/admin/simulation/demo",
        "/demo",
        "/frontend",
        "/frontend/index.html",
        "/frontend/login",
        "/frontend/otp",
        "/frontend/admin",
        "/frontend/demo",
        "/frontend/styles.css",
        "/frontend/app.js",
        "/frontend/sw.js",
        "/frontend/manifest.json",
        "/frontend-reset",
        "/health",
        "/zones",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Allow OPTIONS and known public prefixes
        if (
            request.method == "OPTIONS"
            or path in self.EXEMPT_PATHS
            or any(path.startswith(p) for p in self.EXEMPT_PATH_PREFIXES)
        ):
            return await call_next(request)

        auth_header = request.headers.get("authorization")
        if not auth_header:
            return JSONResponse(status_code=401, content={"detail": "Authorization required"})

        try:
            token = _extract_bearer_token(auth_header)
            payload = jwt_service.decode_token(token, expected_type="access")
            jti = payload.get("jti")
            if not jti or not is_user_session_active(jti):
                return JSONResponse(status_code=401, content={"detail": "Invalid session"})
            # attach payload for handlers
            request.state.user = payload
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

        return await call_next(request)
