from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from database.connection import SessionLocal
from database.models import User, Location, Alert


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_store() -> None:
    """
    Kept for compatibility with the existing LandSense code.
    Database tables are managed by SQLAlchemy/migrations.
    """
    return None


def upsert_user(
    uid: str,
    phone_number: str,
    phone_hash: str,
    name: str | None,
    device_hash: str,
) -> dict[str, Any]:

    now = _utc_iso()
    db = SessionLocal()

    try:
        user = db.get(User, uid)

        if user:
            user.phone_number = phone_number
            user.phone_hash = phone_hash
            user.name = name or user.name or ""
            user.last_login = now
            user.last_device_hash = device_hash
        else:
            user = User(
                uid=uid,
                phone_number=phone_number,
                phone_hash=phone_hash,
                name=name or "",
                created_at=now,
                last_login=now,
                alert_enabled=1,
                last_device_hash=device_hash,
            )
            db.add(user)

        db.commit()
        db.refresh(user)

        return {
            "uid": user.uid,
            "phone_number": user.phone_number,
            "phone_hash": user.phone_hash,
            "name": user.name,
            "created_at": user.created_at,
            "last_login": user.last_login,
            "alert_enabled": user.alert_enabled,
            "last_device_hash": user.last_device_hash,
        }

    except SQLAlchemyError:
        db.rollback()
        raise

    finally:
        db.close()


def get_user(uid: str) -> dict[str, Any] | None:

    db = SessionLocal()

    try:
        user = db.get(User, uid)

        if not user:
            return None

        return {
            "uid": user.uid,
            "phone_number": user.phone_number,
            "phone_hash": user.phone_hash,
            "name": user.name,
            "created_at": user.created_at,
            "last_login": user.last_login,
            "alert_enabled": user.alert_enabled,
            "last_device_hash": user.last_device_hash,
        }

    finally:
        db.close()


def set_alert_subscription(
    uid: str,
    enabled: bool,
) -> None:

    db = SessionLocal()

    try:
        user = db.get(User, uid)

        if not user:
            return

        user.alert_enabled = 1 if enabled else 0
        user.last_login = _utc_iso()

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise

    finally:
        db.close()


def store_location(
    uid: str,
    latitude: float,
    longitude: float,
) -> None:

    db = SessionLocal()

    try:
        location = db.get(Location, uid)
        now = _utc_iso()

        if location:
            location.latitude = latitude
            location.longitude = longitude
            location.last_updated = now
        else:
            location = Location(
                user_id=uid,
                latitude=latitude,
                longitude=longitude,
                last_updated=now,
            )
            db.add(location)

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise

    finally:
        db.close()


def create_alert(
    user_id: str,
    risk_level: str,
    message: str,
    delivered_status: str,
) -> None:

    db = SessionLocal()

    try:
        alert = Alert(
            user_id=user_id,
            risk_level=risk_level,
            message=message,
            timestamp=_utc_iso(),
            delivered_status=delivered_status,
        )

        db.add(alert)
        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise

    finally:
        db.close()


def list_alerts(
    user_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:

    db = SessionLocal()

    try:
        stmt = (
            select(Alert)
            .where(Alert.user_id == user_id)
            .order_by(Alert.id.desc())
            .limit(limit)
        )

        alerts = db.scalars(stmt).all()

        return [
            {
                "user_id": alert.user_id,
                "risk_level": alert.risk_level,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "delivered_status": alert.delivered_status,
            }
            for alert in alerts
        ]

    finally:
        db.close()