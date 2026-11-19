from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
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

    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'Citizen'"),
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
# ADMIN AUDIT EVENTS
# =========================================================

class AuditEvent(Base):
    """Privacy-safe historical record of meaningful Admin operations."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp_utc: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    zone_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    zone_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    risk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column("metadata", Text, nullable=False, server_default=text("'{}'"))


# =========================================================
# DATASET-BACKED LANDSLIDE INVENTORY
# =========================================================

class LandslideInventory(Base):
    """Historical point inventory imported from a controlled dataset."""

    __tablename__ = "landslide_inventory"
    __table_args__ = (
        UniqueConstraint("source_name", "source_record_id", name="uq_landslide_inventory_source_record"),
    )

    event_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    source_record_id: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    initiation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    state: Mapped[str] = mapped_column(String(160), nullable=False)
    district: Mapped[str | None] = mapped_column(String(160), nullable=True)
    subdivision_or_taluk: Mapped[str | None] = mapped_column(String(200), nullable=True)
    material_involved: Mapped[str | None] = mapped_column(String(200), nullable=True)
    movement_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    history_date_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_page: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'dataset'"))
    imported_at: Mapped[str] = mapped_column(String(64), nullable=False)


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
    # =========================================================
# USER SESSIONS
# =========================================================

class UserSession(Base):
    __tablename__ = "user_sessions"

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

    token_jti: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    issued_at: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    expires_at: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    revoked_at: Mapped[str | None] = mapped_column(
        String,
        nullable=True
    )

    last_seen_at: Mapped[str] = mapped_column(
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


# =========================================================
# COMMUNITY HAZARD REPORTS (separate from official inventory/zones)
# =========================================================

class CommunityReport(Base):
    __tablename__ = "community_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reporter_uid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reporter_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    reporter_role: Mapped[str | None] = mapped_column(String(16), nullable=True, server_default=text("'citizen'"))
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    place_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"), index=True)
    reviewed_by_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommunityReportReview(Base):
    __tablename__ = "community_report_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("community_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_uid: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)
