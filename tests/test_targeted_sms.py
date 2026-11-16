from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend_api
import sms_service
from database.connection import get_db


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _SmsDb:
    def __init__(self, rows, scalar_values, existing_user_ids=()):
        self.rows = rows
        self.scalar_values = iter(scalar_values)
        self.existing_user_ids = list(existing_user_ids)
        self.created = []
        self.commits = 0

    def execute(self, _statement):
        return _Rows(self.rows)

    def scalar(self, _statement):
        return next(self.scalar_values, None)

    def scalars(self, _statement):
        return _Rows(self.existing_user_ids)

    def add_all(self, alerts):
        self.created.extend(alerts)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _user(uid, phone, opted_in=True):
    return SimpleNamespace(uid=uid, phone_number=phone, alert_enabled=1 if opted_in else 0)


def _location(latitude=18.4, longitude=73.29):
    return SimpleNamespace(latitude=latitude, longitude=longitude, last_updated="2026-08-15T10:00:00Z")


def _request(send_sms=True):
    return backend_api.AffectedZonePreviewRequest(
        zone_id="RGD-01",
        risk_level="HIGH",
        message="Move away from unstable slopes.",
        duration_minutes=60,
        send_sms=send_sms,
    )


def _configured():
    return {"provider": "twilio", "configured": True, "credentials_present": True, "package_available": True}


def _unconfigured():
    return {"provider": "twilio", "configured": False, "credentials_present": False, "package_available": True}


class TargetedSmsTests(unittest.TestCase):
    def _activate(self, db, *, send_sms=True, configured=True, simulation=False, sms_result=None):
        sender = Mock(return_value=sms_result or {"status": "sent", "provider": "twilio"})
        with (
            patch.object(backend_api, "sms_configuration_status", return_value=_configured() if configured else _unconfigured()),
            patch.object(backend_api, "send_sms_alert", sender),
            patch.object(backend_api, "simulation_mode", SimpleNamespace(read_state=lambda: {"enabled": simulation})),
        ):
            result = backend_api.activate_affected_zone_alert(_request(send_sms), {"role": "Admin"}, db)
        return result, sender

    def test_preview_counts_only_opted_in_inside_zone_users_and_hides_full_phone(self):
        rows = [
            (_user("eligible", "+919876543210"), _location()),
            (_user("opted-out", "+919876543211", False), _location(18.41, 73.28)),
            (_user("bad-phone", "9876543212"), _location(18.42, 73.27)),
            (_user("outside", "+919876543212"), _location(19.0, 74.0)),
        ]
        db = _SmsDb(rows, [4, "HIGH", "LOW", "MEDIUM"])
        with (
            patch.object(backend_api, "sms_configuration_status", return_value=_configured()),
            patch.object(backend_api, "simulation_mode", SimpleNamespace(read_state=lambda: {"enabled": False})),
        ):
            result = backend_api.preview_affected_zone_recipients(_request(False), {"role": "Admin"}, db)

        self.assertEqual(result["recipient_count"], 3)
        self.assertEqual(result["sms_eligible_count"], 1)
        self.assertTrue(all("_sms_phone_number" not in item for item in result["recipients"]))
        self.assertTrue(all("phone_number" not in item for item in result["recipients"]))

    def test_activation_request_rejects_client_recipient_geometry_and_role_fields(self):
        base = {
            "zone_id": "RGD-01",
            "risk_level": "HIGH",
            "message": "Move away from unstable slopes.",
            "duration_minutes": 60,
            "send_sms": True,
        }
        for forbidden in ("user_ids", "phone_numbers", "geometry", "role"):
            with self.subTest(forbidden=forbidden), self.assertRaises(Exception):
                backend_api.AffectedZonePreviewRequest(**base, **{forbidden: ["attacker"]})

    def test_multiple_eligible_users_are_sent_via_mocked_twilio_only(self):
        rows = [
            (_user("one", "+919876543210"), _location()),
            (_user("two", "+919876543211"), _location(18.41, 73.28)),
            (_user("outside", "+919876543299"), _location(19.0, 74.0)),
        ]
        db = _SmsDb(rows, [3, "HIGH", "HIGH"])
        result, sender = self._activate(db)

        self.assertEqual(result["recipient_count"], 2)
        self.assertEqual(result["in_app_created_count"], 2)
        self.assertEqual(result["sms_eligible_count"], 2)
        self.assertEqual(result["sms_attempted"], 2)
        self.assertEqual(result["sms_sent"], 2)
        self.assertEqual(result["status"], "sms_sent")
        self.assertEqual(sender.call_count, 2)
        self.assertTrue(all(call.kwargs["allow_simulated_fallback"] is False for call in sender.call_args_list))
        self.assertNotIn("+919876543299", [call.args[0] for call in sender.call_args_list])

    def test_sms_disabled_and_zero_eligible_users_never_call_provider(self):
        eligible_db = _SmsDb([(_user("one", "+919876543210"), _location())], [1, "HIGH"])
        disabled, disabled_sender = self._activate(eligible_db, send_sms=False)
        self.assertEqual(disabled["status"], "in_app_pending")
        self.assertEqual(disabled["sms_attempted"], 0)
        disabled_sender.assert_not_called()

        opted_out_db = _SmsDb([(_user("off", "+919876543210", False), _location())], [1, "LOW"])
        no_eligible, no_eligible_sender = self._activate(opted_out_db)
        self.assertEqual(no_eligible["status"], "no_sms_eligible")
        self.assertEqual(no_eligible["sms_eligible_count"], 0)
        no_eligible_sender.assert_not_called()

    def test_missing_credentials_suppresses_sms_but_keeps_in_app_alert(self):
        db = _SmsDb([(_user("one", "+919876543210"), _location())], [1, "HIGH"])
        result, sender = self._activate(db, configured=False)

        self.assertEqual(result["status"], "sms_provider_unavailable")
        self.assertEqual(result["in_app_created_count"], 1)
        self.assertEqual(result["sms_attempted"], 0)
        self.assertEqual(result["sms_suppressed"], 1)
        sender.assert_not_called()

    def test_simulation_mode_rejects_real_activation_without_writes_or_provider_call(self):
        db = _SmsDb([(_user("one", "+919876543210"), _location())], [1, "HIGH"])
        sender = Mock()
        with (
            patch.object(backend_api, "send_sms_alert", sender),
            patch.object(backend_api, "simulation_mode", SimpleNamespace(read_state=lambda: {"enabled": True})),
            self.assertRaises(HTTPException) as raised,
        ):
            backend_api.activate_affected_zone_alert(_request(), {"role": "Admin"}, db)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("disabled", raised.exception.detail)
        self.assertEqual(db.created, [])
        self.assertEqual(db.commits, 0)
        sender.assert_not_called()

    def test_batch_limit_refuses_all_sms_without_silent_truncation(self):
        rows = [
            (_user("one", "+919876543210"), _location()),
            (_user("two", "+919876543211"), _location(18.41, 73.28)),
        ]
        db = _SmsDb(rows, [2, "HIGH", "HIGH"])
        with patch.dict(os.environ, {"SMS_MAX_RECIPIENTS": "1"}):
            result, sender = self._activate(db)

        self.assertEqual(result["status"], "sms_batch_limit_exceeded")
        self.assertEqual(result["in_app_created_count"], 2)
        self.assertEqual(result["sms_attempted"], 0)
        self.assertEqual(result["sms_suppressed"], 2)
        sender.assert_not_called()

    def test_duplicate_activation_does_not_resend_sms(self):
        db = _SmsDb(
            [(_user("one", "+919876543210"), _location())],
            [1, "HIGH"],
            existing_user_ids=["one"],
        )
        result, sender = self._activate(db)

        self.assertEqual(result["status"], "deduplicated")
        self.assertEqual(result["in_app_created_count"], 0)
        self.assertEqual(result["sms_attempted"], 0)
        self.assertEqual(result["sms_suppressed"], 1)
        sender.assert_not_called()

    def test_sms_failure_does_not_rollback_in_app_alert(self):
        db = _SmsDb([(_user("one", "+919876543210"), _location())], [1, "HIGH"])
        result, sender = self._activate(db, sms_result={"status": "failed", "provider": "twilio"})

        self.assertEqual(result["status"], "sms_failed")
        self.assertEqual(result["in_app_created_count"], 1)
        self.assertEqual(len(db.created), 1)
        self.assertEqual(db.created[0].delivered_status, "real_in_app_pending")
        self.assertEqual(db.commits, 1)
        self.assertEqual(sender.call_count, 1)

    def test_targeted_missing_credentials_do_not_create_simulated_sms_log(self):
        logger = Mock()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(sms_service, "internet_available", return_value=False),
            patch.object(sms_service, "_log_sms", logger),
        ):
            result = sms_service.send_sms_alert(
                "+919876543210",
                "Test only",
                allow_simulated_fallback=False,
            )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["provider"], "twilio")
        logger.assert_not_called()

    def test_activation_http_authorization_admin_200_citizen_403_missing_401(self):
        db = _SmsDb([(_user("one", "+919876543210"), _location())], [1, "HIGH"])
        backend_api.app.dependency_overrides[get_db] = lambda: db
        client = TestClient(backend_api.app, base_url="https://testserver")
        payload = {
            "zone_id": "RGD-01",
            "risk_level": "HIGH",
            "message": "Move away from unstable slopes.",
            "duration_minutes": 60,
            "send_sms": False,
        }
        try:
            with (
                patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "admin", "jti": "active", "role": "Admin"}),
                patch("backend.auth.middleware.is_user_session_active", return_value=True),
                patch.object(backend_api, "sms_configuration_status", return_value=_unconfigured()),
                patch.object(backend_api, "simulation_mode", SimpleNamespace(read_state=lambda: {"enabled": False})),
            ):
                admin = client.post("/admin/affected-zones/activate", headers={"Authorization": "Bearer admin"}, json=payload)
                missing = client.post("/admin/affected-zones/activate", json=payload)

            with (
                patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "citizen", "jti": "active", "role": "Citizen"}),
                patch("backend.auth.middleware.is_user_session_active", return_value=True),
            ):
                citizen = client.post("/admin/affected-zones/activate", headers={"Authorization": "Bearer citizen"}, json=payload)
        finally:
            backend_api.app.dependency_overrides.clear()

        self.assertEqual(admin.status_code, 200)
        self.assertEqual(citizen.status_code, 403)
        self.assertEqual(missing.status_code, 401)

    def test_direct_http_activation_is_rejected_before_all_work_in_simulation_mode(self):
        db = _SmsDb([(_user("one", "+919876543210"), _location())], [1, "HIGH"])
        backend_api.app.dependency_overrides[get_db] = lambda: db
        selection = Mock(side_effect=AssertionError("recipient calculation must not run"))
        sender = Mock(side_effect=AssertionError("SMS provider must not run"))
        client = TestClient(backend_api.app, base_url="https://testserver")
        payload = {
            "zone_id": "RGD-01", "risk_level": "HIGH", "message": "Safety bypass regression",
            "duration_minutes": 60, "send_sms": True,
        }
        try:
            with (
                patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "admin", "jti": "active", "role": "Admin"}),
                patch("backend.auth.middleware.is_user_session_active", return_value=True),
                patch.object(backend_api, "simulation_mode", SimpleNamespace(read_state=lambda: {"enabled": True})),
                patch.object(backend_api, "_affected_zone_recipients", selection),
                patch.object(backend_api, "send_sms_alert", sender),
            ):
                response = client.post("/admin/affected-zones/activate", headers={"Authorization": "Bearer admin"}, json=payload)
        finally:
            backend_api.app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 409)
        self.assertIn("disabled", response.json()["detail"])
        selection.assert_not_called()
        sender.assert_not_called()
        self.assertEqual(db.created, [])
        self.assertEqual(db.commits, 0)


if __name__ == "__main__":
    unittest.main()
