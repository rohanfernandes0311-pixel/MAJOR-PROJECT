"""Isolated Weatherbit boundary tests; fixtures never become runtime weather."""

import json
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.auth.dependencies import require_auth
from backend.citizen_weather import router
from services.weatherbit_current import CURRENT_WEATHER_URL, WeatherbitUnavailable, fetch_current_weather


OBSERVATION = {
    "temp": 24.8, "rh": 42, "wind_spd": 2.2, "vis": 16, "precip": 0,
    "weather": {"description": "Few clouds"}, "ts": 1780419000,
}


class WeatherbitClientTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"WEATHERBIT_API_KEY": "test-only-private-key"})
        env.start()
        self.addCleanup(env.stop)
        self.response = Mock(status_code=200)
        self.response.json.return_value = {"data": [OBSERVATION]}
        get = patch("services.weatherbit_current.requests.get", return_value=self.response)
        self.get = get.start()
        self.addCleanup(get.stop)

    def test_exact_supplied_coordinates_and_metric_units_are_sent_only_to_weatherbit(self):
        result = fetch_current_weather(12.42, 75.73)
        self.get.assert_called_once_with(
            CURRENT_WEATHER_URL,
            params={"lat": 12.42, "lon": 75.73, "units": "M", "key": "test-only-private-key"},
            timeout=(3.05, 8), allow_redirects=False,
        )
        self.assertEqual(result, {
            "source": "weatherbit", "temperature_c": 24.8, "humidity_pct": 42.0,
            "wind_speed_mps": 2.2, "visibility_km": 16.0,
            "precipitation_mm_per_hour": 0.0, "description": "Few clouds",
            "observed_at": "2026-06-02T16:50:00+00:00",
        })

    def test_missing_fields_remain_null_instead_of_zero(self):
        self.response.json.return_value = {"data": [{"temp": 0}]}
        result = fetch_current_weather(0, 0)
        self.assertEqual(result["temperature_c"], 0)
        for field in ("humidity_pct", "wind_speed_mps", "visibility_km", "precipitation_mm_per_hour", "description", "observed_at"):
            self.assertIsNone(result[field])

    def test_invalid_measurements_do_not_become_fake_values(self):
        self.response.json.return_value = {"data": [{
            "temp": 12, "rh": 101, "wind_spd": -1, "vis": "10", "precip": False, "ts": "bad",
        }]}
        result = fetch_current_weather(12, 75)
        for field in ("humidity_pct", "wind_speed_mps", "visibility_km", "precipitation_mm_per_hour", "observed_at"):
            self.assertIsNone(result[field])

    def test_missing_key_never_contacts_provider(self):
        with patch.dict("os.environ", {"WEATHERBIT_API_KEY": ""}), self.assertRaises(WeatherbitUnavailable):
            fetch_current_weather(12, 75)
        self.get.assert_not_called()

    def test_client_rejects_missing_nonfinite_and_out_of_range_coordinates(self):
        for lat, lon in [(None, 75), (12, None), (float("nan"), 75), (12, float("inf")), (91, 75), (12, -181), (True, 75)]:
            with self.subTest(lat=lat, lon=lon), self.assertRaises(WeatherbitUnavailable):
                fetch_current_weather(lat, lon)
        self.get.assert_not_called()

    def test_upstream_http_failures_and_redirects_never_supply_weather(self):
        for code in (204, 301, 401, 403, 429, 500):
            self.response.status_code = code
            with self.subTest(code=code), self.assertRaisesRegex(WeatherbitUnavailable, r"^Live weather unavailable\.$"):
                fetch_current_weather(12, 75)

    def test_upstream_exceptions_never_expose_key_or_url(self):
        for error in (requests.Timeout("URL?key=test-only-private-key"), requests.ConnectionError("test-only-private-key"), requests.HTTPError("test-only-private-key")):
            self.get.side_effect = error
            with self.subTest(error=type(error)), self.assertRaises(WeatherbitUnavailable) as raised:
                fetch_current_weather(12, 75)
            self.assertEqual(str(raised.exception), "Live weather unavailable.")

    def test_invalid_json_and_empty_payloads_fail_without_fallback(self):
        self.response.json.side_effect = ValueError("test-only-private-key")
        with self.assertRaises(WeatherbitUnavailable):
            fetch_current_weather(12, 75)
        self.response.json.side_effect = None
        for body in (None, [], {}, {"data": []}, {"data": [None]}, {"data": [{}]}, {"data": [{"temp": float("nan")}]}):
            self.response.json.return_value = body
            with self.subTest(body=body), self.assertRaises(WeatherbitUnavailable):
                fetch_current_weather(12, 75)

    def test_only_allowlisted_fields_are_returned(self):
        self.response.json.return_value = {"data": [{**OBSERVATION, "key": "test-only-private-key", "token": "private"}], "error": "test-only-private-key"}
        self.assertNotIn("test-only-private-key", json.dumps(fetch_current_weather(12, 75)))

    def test_key_echo_in_description_is_rejected(self):
        self.response.json.return_value = {"data": [{**OBSERVATION, "weather": {"description": "test-only-private-key"}}]}
        with self.assertRaises(WeatherbitUnavailable):
            fetch_current_weather(12, 75)

    def test_provider_observation_time_is_used_without_inventing_update_time(self):
        self.response.json.return_value = {"data": [{"temp": 12, "ob_time": "2026-06-02 16:50"}]}
        self.assertEqual(fetch_current_weather(12, 75)["observed_at"], "2026-06-02T16:50:00+00:00")


class CitizenWeatherEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[require_auth] = lambda: {"sub": "fixture", "role": "Citizen"}
        self.client = TestClient(self.app)
        client = patch("backend.citizen_weather.fetch_current_weather", return_value={"source": "weatherbit", "temperature_c": 24.8})
        self.fetch = client.start()
        self.addCleanup(client.stop)

    def test_valid_coordinates_are_passed_to_new_client_and_response_is_not_cached(self):
        response = self.client.get("/citizen/weather/current?latitude=12.42&longitude=75.73")
        self.assertEqual(response.status_code, 200)
        self.fetch.assert_called_once_with(12.42, 75.73)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_missing_latitude_is_rejected_without_default(self):
        self.assertEqual(self.client.get("/citizen/weather/current?longitude=75").status_code, 422)
        self.fetch.assert_not_called()

    def test_missing_longitude_is_rejected_without_default(self):
        self.assertEqual(self.client.get("/citizen/weather/current?latitude=12").status_code, 422)
        self.fetch.assert_not_called()

    def test_invalid_latitude_is_rejected(self):
        for value in ("91", "-91", "nan", "inf", "bad"):
            with self.subTest(value=value):
                self.assertEqual(self.client.get(f"/citizen/weather/current?latitude={value}&longitude=75").status_code, 422)
        self.fetch.assert_not_called()

    def test_invalid_longitude_is_rejected(self):
        for value in ("181", "-181", "nan", "-inf", "bad"):
            with self.subTest(value=value):
                self.assertEqual(self.client.get(f"/citizen/weather/current?latitude=12&longitude={value}").status_code, 422)
        self.fetch.assert_not_called()

    def test_unavailable_response_contains_no_weather_or_secret(self):
        self.fetch.side_effect = WeatherbitUnavailable()
        response = self.client.get("/citizen/weather/current?latitude=12&longitude=75")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Live weather unavailable."})
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_existing_authentication_dependency_is_required(self):
        self.app.dependency_overrides.clear()
        with patch("backend.auth.dependencies.authenticate_profile", side_effect=HTTPException(status_code=401, detail="Unauthorized")):
            response = self.client.get("/citizen/weather/current?latitude=12&longitude=75")
        self.assertEqual(response.status_code, 401)
        self.fetch.assert_not_called()

    def test_registered_endpoint_uses_existing_jwt_middleware(self):
        import backend_api
        with patch("backend.auth.middleware.jwt_service.decode_token", side_effect=HTTPException(status_code=401, detail="Invalid token")):
            client = TestClient(backend_api.app, base_url="https://testserver")
            self.assertEqual(client.get("/citizen/weather/current?latitude=12&longitude=75").status_code, 401)
            self.assertEqual(client.get("/citizen/weather/current?latitude=12&longitude=75", headers={"Authorization": "Bearer invalid"}).status_code, 401)
        self.fetch.assert_not_called()

    def test_weather_request_never_calls_prediction_weather_database_or_routing(self):
        import backend_api
        overrides = backend_api.app.dependency_overrides.copy()
        backend_api.app.dependency_overrides[require_auth] = lambda: {"sub": "fixture", "role": "Citizen"}
        def restore_overrides():
            backend_api.app.dependency_overrides.clear()
            backend_api.app.dependency_overrides.update(overrides)
        self.addCleanup(restore_overrides)
        with (
            patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "fixture", "jti": "test-session", "role": "Citizen"}),
            patch("backend.auth.middleware.is_user_session_active", return_value=True),
            patch("services.weather_extension.WeatherExtensionService.fetch_weather_context", side_effect=AssertionError("prediction weather called")),
            patch.object(backend_api, "predict", side_effect=AssertionError("ML called")),
            patch.object(backend_api, "store_location", side_effect=AssertionError("location persisted")),
            patch.object(backend_api, "plan_safe_route", side_effect=AssertionError("routing called")),
        ):
            client = TestClient(backend_api.app, base_url="https://testserver")
            response = client.get("/citizen/weather/current?latitude=12&longitude=75", headers={"Authorization": "Bearer test-access-token"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["source"], "weatherbit")
            self.fetch.assert_called_once_with(12, 75)
