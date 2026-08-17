"""HTTP-level Phase 5.7 security and protected-endpoint regression checks."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend_api
from backend.auth.dependencies import get_current_auth_payload, require_auth
from database.connection import get_db


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ScopedAlertDb:
    def __init__(self):
        self.requested_user = None
        self.alerts = [
            SimpleNamespace(
                id=10,
                user_id="user-a",
                risk_level="HIGH",
                message="A only",
                timestamp="2026-08-15T10:00:00Z",
                delivered_status="in_app_pending",
            ),
            SimpleNamespace(
                id=11,
                user_id="user-b",
                risk_level="HIGH",
                message="B only",
                timestamp="2026-08-15T10:01:00Z",
                delivered_status="in_app_pending",
            ),
        ]

    def scalars(self, statement):
        compiled = statement.compile()
        self.requested_user = next(value for key, value in compiled.params.items() if "user_id" in key)
        return _Rows([item for item in self.alerts if item.user_id == self.requested_user])


class Phase57HttpRegressionTests(unittest.TestCase):
    def setUp(self):
        self.db = _ScopedAlertDb()
        backend_api.app.dependency_overrides[require_auth] = lambda: {
            "sub": "user-a",
            "role": "Citizen",
        }
        backend_api.app.dependency_overrides[get_current_auth_payload] = lambda: {
            "sub": "user-a",
            "phone": "+911234567890",
            "role": "Citizen",
        }
        backend_api.app.dependency_overrides[get_db] = lambda: self.db
        self.jwt_patch = patch(
            "backend.auth.middleware.jwt_service.decode_token",
            return_value={"sub": "user-a", "jti": "active-session", "role": "Citizen"},
        )
        self.session_patch = patch(
            "backend.auth.middleware.is_user_session_active", return_value=True
        )
        self.jwt_patch.start()
        self.session_patch.start()
        self.client = TestClient(backend_api.app, base_url="https://testserver")
        self.auth = {"Authorization": "Bearer test-access-token"}

    def tearDown(self):
        backend_api.app.dependency_overrides.clear()
        self.session_patch.stop()
        self.jwt_patch.stop()

    def test_alerts_my_is_authenticated_and_query_cannot_select_another_user(self):
        authenticated = self.client.get(
            "/alerts/my?user_id=user-b", headers=self.auth
        )
        unauthenticated = self.client.get("/alerts/my")

        self.assertEqual(authenticated.status_code, 200)
        self.assertEqual(authenticated.json()["count"], 1)
        self.assertEqual(authenticated.json()["alerts"][0]["message"], "A only")
        self.assertNotIn("user_id", authenticated.json()["alerts"][0])
        self.assertEqual(self.db.requested_user, "user-a")
        self.assertEqual(unauthenticated.status_code, 401)

    def test_existing_protected_dashboard_endpoints_still_return_200(self):
        predict_body = {
            "latitude": 18.55,
            "longitude": 73.9,
            "deformation_mm": 5,
            "velocity_mm_yr": 12,
            "coherence": 0.8,
            "slope_deg": 24,
            "soil_moisture_pct": 45,
        }
        location_body = {"user_id": "client-value-is-overridden", **predict_body}
        route_body = {
            "start_latitude": 18.55,
            "start_longitude": 73.9,
            "end_latitude": 18.56,
            "end_longitude": 73.91,
        }

        with (
            patch.object(
                backend_api,
                "weather_service",
                SimpleNamespace(
                    fetch_weather_context=lambda *_: {},
                    fetch_rainfall_mm=lambda *_: {"rainfall_mm": 0},
                ),
            ),
            patch.object(backend_api, "predict", return_value={"risk_label": "LOW"}),
            patch.object(backend_api, "load_zones", return_value={"features": []}),
            patch.object(backend_api, "find_zone_matches", return_value=[]),
            patch.object(
                backend_api,
                "safe_route_service",
                SimpleNamespace(build_guidance=lambda *_args, **_kwargs: None),
            ),
            patch.object(backend_api, "_evaluate_location", return_value={"final_risk": "LOW"}) as evaluate,
            patch.object(backend_api, "store_location") as store_location,
            patch.object(backend_api, "plan_safe_route", return_value={"status": "ok", "path": []}),
        ):
            prediction = self.client.post("/predict-risk", headers=self.auth, json=predict_body)
            location = self.client.post("/location-update", headers=self.auth, json=location_body)
            route = self.client.post("/route-safe", headers=self.auth, json=route_body)

        self.assertEqual(prediction.status_code, 200)
        self.assertEqual(location.status_code, 200)
        self.assertEqual(route.status_code, 200)
        self.assertEqual(evaluate.call_args.args[0].user_id, "user-a")
        store_location.assert_called_once_with("user-a", 18.55, 73.9)

    def test_existing_profile_and_admin_frontend_routes_still_return_200(self):
        profile = self.client.get("/profile", headers=self.auth)
        admin = self.client.get("/admin")

        self.assertEqual(profile.status_code, 200)
        self.assertTrue(profile.json()["authenticated"])
        self.assertEqual(admin.status_code, 200)


if __name__ == "__main__":
    unittest.main()
