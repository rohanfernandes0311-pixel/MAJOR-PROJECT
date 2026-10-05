"""Explicitly simulated transports for the Admin offline-alert demonstration.

These transports never contact an external provider.  Their small interface is
intentionally replaceable by a future native/mobile transport without allowing
the browser demonstration to claim a physical delivery occurred.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OfflineAlertTransport:
    channel: str

    def simulate(self, recipient: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "recipient": recipient["displayId"],
            "status": "SIMULATED",
            "message": message,
            "physical_delivery": False,
        }


class SmsDemoTransport(OfflineAlertTransport):
    def __init__(self) -> None:
        super().__init__("SMS_DEMO")


class BluetoothDemoTransport(OfflineAlertTransport):
    def __init__(self) -> None:
        super().__init__("BLUETOOTH_DEMO")


DEMO_TRANSPORTS: dict[str, OfflineAlertTransport] = {
    "SMS_DEMO": SmsDemoTransport(),
    "BLUETOOTH_DEMO": BluetoothDemoTransport(),
}


def simulate_offline_deliveries(
    recipients: list[dict[str, Any]], channels: list[str], message: str
) -> list[dict[str, Any]]:
    """Return local demo delivery records; perform no I/O or provider calls."""
    return [
        DEMO_TRANSPORTS[channel].simulate(recipient, message)
        for recipient in recipients
        for channel in channels
    ]
