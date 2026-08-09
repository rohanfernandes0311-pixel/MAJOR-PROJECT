from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .connection import Base


# =========================================================
# USERS
# =========================================================

class User(Base):
    __tablename__ = "users"

    uid: Mapped[str] = mapped_column(
        String,
        primary_key=True
    )

    phone_number: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    phone_hash: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    name: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    last_login: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    alert_enabled: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    last_device_hash: Mapped[str] = mapped_column(
        String,
        nullable=False
    )


# =========================================================
# LOCATIONS
# =========================================================

class Location(Base):
    __tablename__ = "locations"

    user_id: Mapped[str] = mapped_column(
        String,
        primary_key=True
    )

    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    last_updated: Mapped[str] = mapped_column(
        String,
        nullable=False
    )


# =========================================================
# ALERTS
# =========================================================

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    user_id: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    risk_level: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    message: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    timestamp: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    delivered_status: Mapped[str] = mapped_column(
        String,
        nullable=False
    )


# =========================================================
# LOCATION EVENTS
# =========================================================

class LocationEvent(Base):
    __tablename__ = "location_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    user_id: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    timestamp_utc: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    rainfall_mm: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    ml_risk: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    zone_risk: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    final_risk: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    geofence_event: Mapped[str | None] = mapped_column(
        String,
        nullable=True
    )

    active_zone_id: Mapped[str | None] = mapped_column(
        String,
        nullable=True
    )


# =========================================================
# LOGIN HISTORY
# =========================================================

class LoginHistory(Base):
    __tablename__ = "login_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    phone_number: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    phone_hash: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    session_id: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    login_time: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    ip: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    user_agent: Mapped[str | None] = mapped_column(
        String,
        nullable=True
    )


# =========================================================
# OTP SESSIONS
# =========================================================

class OTPSession(Base):
    __tablename__ = "otp_sessions"

    session_id: Mapped[str] = mapped_column(
        String,
        primary_key=True
    )

    phone_number: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    phone_hash: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    otp_hash: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    otp_salt: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    verified: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    revoked: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    resend_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    expires_at: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    resend_after_at: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    updated_at: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    last_sent_at: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    last_ip: Mapped[str | None] = mapped_column(
        String,
        nullable=True
    )

    last_user_agent: Mapped[str | None] = mapped_column(
        String,
        nullable=True
    )