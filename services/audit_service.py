from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.models import AuditEvent


EVENT_DEFINITIONS: dict[str, tuple[str, str]] = {
    "ZONE_SELECTED": ("ADMIN_ACTION", "INFO"),
    "INTELLIGENCE_CALCULATED": ("INTELLIGENCE", "INFO"),
    "INTELLIGENCE_UNAVAILABLE": ("INTELLIGENCE", "WARNING"),
    "INCIDENT_SELECTED": ("INCIDENT", "INFO"),
    "AFFECTED_POPULATION_CALCULATED": ("INTELLIGENCE", "INFO"),
    "RECIPIENT_PREVIEW_OPENED": ("ADMIN_ACTION", "INFO"),
    "ALERT_ACTIVATED": ("ALERT", "CRITICAL"),
    "ALERT_ACTIVATION_FAILED": ("ALERT", "WARNING"),
    "SIMULATION_STARTED": ("SIMULATION", "INFO"),
    "SIMULATION_STOPPED": ("SIMULATION", "INFO"),
    "DEMO_INCIDENT_LAUNCHED": ("SIMULATION", "INFO"),
    "DEMO_ALERT_GENERATED": ("SIMULATION", "INFO"),
    "OFFLINE_DEMO_ALERT_COMPLETED": ("SIMULATION", "INFO"),
}
ALLOWED_MODES = {"REAL", "SIMULATION", "DEMO"}
ALLOWED_RISKS = {"SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
SAFE_METADATA_KEYS = {
    "confidence", "dataQuality", "recommendedAction", "automaticAlert",
    "affectedStatus", "realUsersInside", "realUsersOutside", "eligibleRecipients",
    "smsEligibleRecipients", "totalRegisteredUsers", "recipientCount", "status",
    "smsRequested", "smsSent", "smsFailed", "smsSuppressed", "incidentTitle",
    "incidentStatus", "sourceLabel", "locationPrecision", "simulatedParticipants",
    "reason", "scenarioName", "forcedRisk", "externalNotificationsSuppressed",
    "channels", "smsDemoCount", "bluetoothDemoCount", "realSmsCount",
    "realBluetoothCount", "realAlertCount", "offlineDeliverySimulation",
}
SENSITIVE_FRAGMENTS = {
    "phone", "otp", "password", "token", "jwt", "firebase", "twilio", "credential",
    "authorization", "latitude", "longitude", "gps", "user_id", "userId",
}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] if text else None


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if key not in SAFE_METADATA_KEYS or any(fragment.lower() in key.lower() for fragment in SENSITIVE_FRAGMENTS):
            continue
        if value is None or isinstance(value, (bool, int, float)):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value[:300]
        elif key == "channels" and isinstance(value, list):
            safe[key] = [
                channel for channel in value
                if channel in {"SMS_DEMO", "BLUETOOTH_DEMO"}
            ][:2]
    return safe


def record_audit_event(
    db: Session,
    *,
    event_type: str,
    mode: str,
    message: str,
    zone_id: str | None = None,
    zone_name: str | None = None,
    risk: str | None = None,
    metadata: dict[str, Any] | None = None,
    dedupe_seconds: int = 0,
) -> AuditEvent:
    normalized_type = str(event_type).strip().upper()
    if normalized_type not in EVENT_DEFINITIONS:
        raise ValueError("Unsupported audit event type")
    normalized_mode = str(mode).strip().upper()
    if normalized_mode not in ALLOWED_MODES:
        raise ValueError("Unsupported audit event mode")
    normalized_risk = str(risk).strip().upper() if risk else None
    if normalized_risk not in ALLOWED_RISKS:
        normalized_risk = None
    safe_zone_id = _safe_text(zone_id, 100)
    safe_zone_name = _safe_text(zone_name, 200)

    if dedupe_seconds > 0:
        previous = db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.event_type == normalized_type,
                AuditEvent.mode == normalized_mode,
                AuditEvent.zone_id == safe_zone_id,
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        ).first()
        if previous:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(previous.timestamp_utc)).total_seconds()
                if age <= dedupe_seconds:
                    return previous
            except (TypeError, ValueError):
                pass

    category, severity = EVENT_DEFINITIONS[normalized_type]
    event = AuditEvent(
        timestamp_utc=utc_iso(),
        event_type=normalized_type,
        category=category,
        severity=severity,
        mode=normalized_mode,
        zone_id=safe_zone_id,
        zone_name=safe_zone_name,
        risk=normalized_risk,
        message=_safe_text(message, 500) or normalized_type.replace("_", " ").title(),
        metadata_json=json.dumps(sanitize_metadata(metadata), separators=(",", ":"), sort_keys=True),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def try_record_audit_event(db: Any, **values: Any) -> AuditEvent | None:
    """Keep primary operations available if audit persistence itself is degraded."""
    if not all(hasattr(db, method) for method in ("add", "commit", "refresh", "scalars")):
        return None
    try:
        return record_audit_event(db, **values)
    except (SQLAlchemyError, TypeError, ValueError):
        try:
            db.rollback()
        except Exception:
            pass
        return None


def public_audit_event(event: AuditEvent) -> dict[str, Any]:
    try:
        metadata = json.loads(event.metadata_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        metadata = {}
    return {
        "eventId": f"AUD-{int(event.id):08d}",
        "timestampUtc": event.timestamp_utc,
        "eventType": event.event_type,
        "category": event.category,
        "severity": event.severity,
        "mode": event.mode,
        "zoneId": event.zone_id,
        "zoneName": event.zone_name,
        "risk": event.risk,
        "message": event.message,
        "metadata": sanitize_metadata(metadata if isinstance(metadata, dict) else {}),
    }
