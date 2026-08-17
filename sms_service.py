"""SMS alert service with Twilio and offline simulation fallback."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


SMS_LOG_DIR = Path(__file__).parent / "alerts"
SMS_LOG_DIR.mkdir(exist_ok=True)
SMS_LOG_FILE = SMS_LOG_DIR / "sms_log.jsonl"


def sms_configuration_status() -> dict[str, object]:
    """Return non-secret Twilio readiness metadata for controlled delivery."""
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_phone = os.getenv("TWILIO_SMS_FROM", "").strip()
    try:
        from twilio.rest import Client as _  # noqa: F401
        package_available = True
    except Exception:
        package_available = False
    return {
        "provider": "twilio",
        "configured": bool(sid and token and from_phone and package_available),
        "credentials_present": bool(sid and token and from_phone),
        "package_available": package_available,
        "unavailable_behavior": "simulated_offline",
    }


def internet_available(test_url: str = "https://www.google.com") -> bool:
    try:
        requests.get(test_url, timeout=4)
        return True
    except Exception:
        return False


def _log_sms(payload: dict) -> None:
    with SMS_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def send_sms_alert(phone_number: str, message: str, *, allow_simulated_fallback: bool = True) -> dict:
    """
    Sends SMS through Twilio if configured.
    If credentials/network unavailable, writes a simulated offline SMS event.
    """
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_phone = os.getenv("TWILIO_SMS_FROM", "").strip()

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phone_number": phone_number,
        "message": message,
        "channel": "sms",
    }

    if sid and token and from_phone and internet_available():
        try:
            from twilio.rest import Client

            client = Client(sid, token)
            result = client.messages.create(body=message[:320], from_=from_phone, to=phone_number)
            payload["status"] = "sent"
            payload["provider"] = "twilio"
            payload["message_sid"] = str(result.sid or "")
            _log_sms(payload)
            return payload
        except Exception as exc:
            payload["status"] = "failed"
            payload["provider"] = "twilio"
            payload["error"] = str(exc)
            _log_sms(payload)
            return payload

    payload["status"] = "simulated_offline" if allow_simulated_fallback else "unavailable"
    payload["provider"] = "gsm_fallback" if allow_simulated_fallback else "twilio"
    if allow_simulated_fallback:
        _log_sms(payload)
    return payload
