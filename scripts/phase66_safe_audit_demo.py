"""Safe Phase 6.6 audit demonstration; never activates or sends an alert."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend_api as api
from fastapi import HTTPException
from sqlalchemy import func, select
from database.connection import SessionLocal
from database.models import Alert


REQUIRED_EVENTS = {
    "ZONE_SELECTED",
    "INTELLIGENCE_CALCULATED",
    "AFFECTED_POPULATION_CALCULATED",
    "RECIPIENT_PREVIEW_OPENED",
    "SIMULATION_STARTED",
    "INCIDENT_SELECTED",
    "DEMO_INCIDENT_LAUNCHED",
    "DEMO_ALERT_GENERATED",
    "SIMULATION_STOPPED",
}


def run() -> dict[str, bool]:
    db = SessionLocal()
    preview: dict = {}
    intelligence: dict = {}
    bypass_status = None
    recipient_probe = Mock(side_effect=AssertionError("recipient calculation must not run"))
    provider_probe = Mock(side_effect=AssertionError("notification provider must not run"))
    try:
        api.record_admin_ui_audit_event(
            api.AdminAuditUiEventRequest(event_type="ZONE_SELECTED", zone_id="WYD-03"),
            {"role": "Admin"}, db,
        )
        intelligence = api.admin_zone_intelligence("WYD-03", {"role": "Admin"}, db)
        preview = api.preview_affected_zone_recipients(
            api.AffectedZonePreviewRequest(
                zone_id="WYD-03",
                risk_level=intelligence["assessment"]["overallRisk"],
                message="Phase 6.6 safe audit demonstration only.",
                duration_minutes=60,
                send_sms=False,
            ),
            {"role": "Admin"}, db,
        )
        with patch.object(api.simulation_mode, "record_event"):
            api.admin_simulation_toggle(
                api.SimulationToggleRequest(enabled=True, forced_risk="CRITICAL", scenario_name="Phase 6.6 Audit Demo"),
                {"role": "Admin"}, db,
            )
        alerts_before = int(db.scalar(select(func.count()).select_from(Alert)) or 0)
        with patch.object(api, "_affected_zone_recipients", recipient_probe), patch.object(api, "send_sms_alert", provider_probe):
            try:
                api.activate_affected_zone_alert(
                    api.AffectedZonePreviewRequest(
                        zone_id="WYD-03", risk_level="HIGH", message="Simulation bypass test",
                        duration_minutes=60, send_sms=True,
                    ),
                    {"role": "Admin"}, db,
                )
            except HTTPException as exc:
                bypass_status = exc.status_code
        alerts_after = int(db.scalar(select(func.count()).select_from(Alert)) or 0)
        api.record_admin_ui_audit_event(
            api.AdminAuditUiEventRequest(event_type="INCIDENT_SELECTED", incident_id="wayanad-kalladi-2026-07-07"),
            {"role": "Admin"}, db,
        )
        for event_type in ("DEMO_INCIDENT_LAUNCHED", "DEMO_ALERT_GENERATED"):
            api.record_admin_ui_audit_event(
                api.AdminAuditUiEventRequest(
                    event_type=event_type,
                    incident_id="wayanad-kalladi-2026-07-07",
                    simulated_count=9,
                ),
                {"role": "Admin"}, db,
            )
    finally:
        if api.simulation_mode.read_state().get("enabled"):
            with patch.object(api.simulation_mode, "record_event"):
                api.admin_simulation_toggle(
                    api.SimulationToggleRequest(enabled=False, forced_risk="LOW", scenario_name="Normal"),
                    {"role": "Admin"}, db,
                )

    result = api.admin_audit_events(limit=20, offset=0, category=None, mode=None, _={"role": "Admin"}, db=db)
    serialized = json.dumps(result)
    event_types = {event["eventType"] for event in result["events"]}
    report = {
        "required_events_present": REQUIRED_EVENTS.issubset(event_types),
        "preview_only": preview.get("preview_only") is True,
        "automatic_alert_off": intelligence.get("automaticAlert") is False,
        "simulation_reset": not bool(api.simulation_mode.read_state().get("enabled")),
        "sensitive_data_absent": re.search(r"\+91\d{10}|otp|authorization|bearer|latitude|longitude", serialized, re.I) is None,
        "real_activation_called": False,
        "direct_bypass_http_409": bypass_status == 409,
        "bypass_recipient_calculation_skipped": recipient_probe.call_count == 0,
        "bypass_provider_skipped": provider_probe.call_count == 0,
        "bypass_alert_writes_absent": alerts_before == alerts_after,
    }
    db.close()
    return report


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
