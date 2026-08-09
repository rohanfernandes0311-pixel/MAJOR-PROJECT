from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from database.connection import SessionLocal
from database.models import OTPSession, UserSession, LoginHistory


OTP_PEPPER = os.getenv(
    "OTP_HASH_PEPPER",
    os.getenv("JWT_SECRET", "change-this-in-production"),
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_store() -> None:
    """
    Kept for compatibility with existing application code.
    Schema is managed by SQLAlchemy/migrations.
    """
    return None


def hash_phone(phone_number: str) -> str:
    data = f"{OTP_PEPPER}:{phone_number.strip()}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_otp(
    otp: str,
    otp_salt: str,
    phone_hash: str,
) -> str:
    return hmac.new(
        OTP_PEPPER.encode("utf-8"),
        f"{phone_hash}:{otp_salt}:{otp.strip()}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _otp_to_dict(session: OTPSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "phone_number": session.phone_number,
        "phone_hash": session.phone_hash,
        "otp_hash": session.otp_hash,
        "otp_salt": session.otp_salt,
        "attempts": session.attempts,
        "verified": session.verified,
        "revoked": session.revoked,
        "resend_count": session.resend_count,
        "expires_at": session.expires_at,
        "resend_after_at": session.resend_after_at,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "last_sent_at": session.last_sent_at,
        "last_ip": session.last_ip,
        "last_user_agent": session.last_user_agent,
    }


def _user_session_to_dict(
    session: UserSession,
) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "phone_number": session.phone_number,
        "phone_hash": session.phone_hash,
        "token_jti": session.token_jti,
        "issued_at": session.issued_at,
        "expires_at": session.expires_at,
        "revoked_at": session.revoked_at,
        "last_seen_at": session.last_seen_at,
        "last_ip": session.last_ip,
        "last_user_agent": session.last_user_agent,
    }


def create_otp_session(
    *,
    phone_number: str,
    otp_hash: str,
    otp_salt: str,
    expires_at: str,
    resend_after_at: str,
    last_ip: str,
    last_user_agent: str,
) -> dict[str, Any]:

    now = _utc_iso()
    session_id = str(uuid.uuid4())
    phone_hash = hash_phone(phone_number)

    db = SessionLocal()

    try:
        db.query(OTPSession).filter(
            OTPSession.phone_number == phone_number,
            OTPSession.verified == 0,
            OTPSession.revoked == 0,
        ).update(
            {
                OTPSession.revoked: 1,
                OTPSession.updated_at: now,
            },
            synchronize_session=False,
        )

        session = OTPSession(
            session_id=session_id,
            phone_number=phone_number,
            phone_hash=phone_hash,
            otp_hash=otp_hash,
            otp_salt=otp_salt,
            attempts=0,
            verified=0,
            revoked=0,
            resend_count=0,
            expires_at=expires_at,
            resend_after_at=resend_after_at,
            created_at=now,
            updated_at=now,
            last_sent_at=now,
            last_ip=last_ip,
            last_user_agent=last_user_agent,
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        return _otp_to_dict(session)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_active_otp_session(
    phone_number: str,
) -> dict[str, Any] | None:

    db = SessionLocal()

    try:
        session = (
            db.query(OTPSession)
            .filter(
                OTPSession.phone_number == phone_number,
                OTPSession.verified == 0,
                OTPSession.revoked == 0,
            )
            .order_by(OTPSession.created_at.desc())
            .first()
        )

        return _otp_to_dict(session) if session else None

    finally:
        db.close()


def get_otp_session(
    *,
    session_id: str,
) -> dict[str, Any] | None:

    db = SessionLocal()

    try:
        session = db.get(OTPSession, session_id)
        return _otp_to_dict(session) if session else None

    finally:
        db.close()


def increment_otp_attempts(
    session_id: str,
) -> dict[str, Any] | None:

    db = SessionLocal()

    try:
        session = db.get(OTPSession, session_id)

        if session:
            session.attempts += 1
            session.updated_at = _utc_iso()

            db.commit()
            db.refresh(session)

        return _otp_to_dict(session) if session else None

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def mark_otp_verified(
    session_id: str,
) -> dict[str, Any] | None:

    db = SessionLocal()

    try:
        session = db.get(OTPSession, session_id)

        if session:
            session.verified = 1
            session.updated_at = _utc_iso()

            db.commit()
            db.refresh(session)

        return _otp_to_dict(session) if session else None

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def revoke_otp_session(
    session_id: str,
) -> None:

    db = SessionLocal()

    try:
        session = db.get(OTPSession, session_id)

        if session:
            session.revoked = 1
            session.updated_at = _utc_iso()
            db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def delete_otp_session(
    session_id: str,
) -> None:

    db = SessionLocal()

    try:
        session = db.get(OTPSession, session_id)

        if session:
            db.delete(session)
            db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def create_user_session(
    *,
    session_id: str,
    phone_number: str,
    token_jti: str,
    issued_at: str,
    expires_at: str,
    last_ip: str,
    last_user_agent: str,
) -> dict[str, Any] | None:

    phone_hash = hash_phone(phone_number)

    db = SessionLocal()

    try:
        session = UserSession(
            session_id=session_id,
            phone_number=phone_number,
            phone_hash=phone_hash,
            token_jti=token_jti,
            issued_at=issued_at,
            expires_at=expires_at,
            revoked_at=None,
            last_seen_at=issued_at,
            last_ip=last_ip,
            last_user_agent=last_user_agent,
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        return _user_session_to_dict(session)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_user_session_by_jti(
    token_jti: str,
) -> dict[str, Any] | None:

    db = SessionLocal()

    try:
        session = (
            db.query(UserSession)
            .filter(UserSession.token_jti == token_jti)
            .first()
        )

        return _user_session_to_dict(session) if session else None

    finally:
        db.close()


def revoke_user_session(
    token_jti: str,
) -> bool:

    db = SessionLocal()

    try:
        session = (
            db.query(UserSession)
            .filter(
                UserSession.token_jti == token_jti,
                UserSession.revoked_at.is_(None),
            )
            .first()
        )

        if not session:
            return False

        now = _utc_iso()
        session.revoked_at = now
        session.last_seen_at = now

        db.commit()

        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def is_user_session_active(
    token_jti: str,
) -> bool:

    session = get_user_session_by_jti(token_jti)

    return bool(session) and not session.get("revoked_at")


def log_login_history(
    *,
    phone_number: str,
    session_id: str,
    status: str,
    ip: str,
    user_agent: str,
) -> None:

    db = SessionLocal()

    try:
        record = LoginHistory(
            phone_number=phone_number,
            phone_hash=hash_phone(phone_number),
            session_id=session_id,
            status=status,
            login_time=_utc_iso(),
            ip=ip,
            user_agent=user_agent,
        )

        db.add(record)
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()