from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import requests

try:
    from twilio.rest import Client as TwilioClient
except Exception:  # pragma: no cover - optional dependency fallback
    TwilioClient = None


@dataclass(slots=True)
class SMSResult:
    status: str
    provider: str
    message_id: str | None = None
    detail: str | None = None


class SMSProvider(Protocol):
    name: str

    def send(self, phone_number: str, message: str) -> SMSResult:
        ...


class MockSMSProvider:
    name = "mock"

    def send(self, phone_number: str, message: str) -> SMSResult:
        _ = (phone_number, message)
        return SMSResult(status="sent", provider=self.name, message_id="mock-message")


class TwilioSMSProvider:
    name = "twilio"

    def __init__(self) -> None:
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        self.from_number = os.getenv("TWILIO_SMS_FROM", "").strip()

    def send(self, phone_number: str, message: str) -> SMSResult:
        if not all([self.account_sid, self.auth_token, self.from_number, TwilioClient]):
            return SMSResult(status="unavailable", provider=self.name, detail="Twilio is not configured")
        client = TwilioClient(self.account_sid, self.auth_token)
        sent = client.messages.create(body=message, from_=self.from_number, to=phone_number)
        return SMSResult(status="sent", provider=self.name, message_id=getattr(sent, "sid", None))


class MSG91SMSProvider:
    name = "msg91"

    def __init__(self) -> None:
        self.api_key = os.getenv("MSG91_AUTH_KEY", "").strip()
        self.sender_id = os.getenv("MSG91_SENDER_ID", "LANDSE").strip()
        self.template_id = os.getenv("MSG91_TEMPLATE_ID", "").strip()
        self.route = os.getenv("MSG91_ROUTE", "4").strip()

    def send(self, phone_number: str, message: str) -> SMSResult:
        if not self.api_key or not self.template_id:
            return SMSResult(status="unavailable", provider=self.name, detail="MSG91 is not configured")

        payload = {
            "flow_id": self.template_id,
            "sender": self.sender_id,
            "mobiles": phone_number.lstrip("+"),
            "message": message,
        }
        response = requests.post(
            "https://control.msg91.com/api/v5/flow/",
            headers={"authkey": self.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        return SMSResult(status="sent" if response.ok else "failed", provider=self.name, detail=response.text[:240])


class Fast2SMSSMSProvider:
    name = "fast2sms"

    def __init__(self) -> None:
        self.api_key = os.getenv("FAST2SMS_API_KEY", "").strip()
        self.sender_id = os.getenv("FAST2SMS_SENDER_ID", "LANDSE").strip()

    def send(self, phone_number: str, message: str) -> SMSResult:
        if not self.api_key:
            return SMSResult(status="unavailable", provider=self.name, detail="Fast2SMS is not configured")

        response = requests.post(
            "https://www.fast2sms.com/dev/bulkV2",
            headers={"authorization": self.api_key, "Content-Type": "application/json"},
            json={
                "route": "q",
                "numbers": phone_number.lstrip("+"),
                "message": message,
                "sender_id": self.sender_id,
            },
            timeout=10,
        )
        return SMSResult(status="sent" if response.ok else "failed", provider=self.name, detail=response.text[:240])


def build_sms_provider() -> SMSProvider:
    provider_name = os.getenv("SMS_PROVIDER", "mock").strip().lower()
    if provider_name == "twilio":
        return TwilioSMSProvider()
    if provider_name == "msg91":
        return MSG91SMSProvider()
    if provider_name == "fast2sms":
        return Fast2SMSSMSProvider()
    return MockSMSProvider()
