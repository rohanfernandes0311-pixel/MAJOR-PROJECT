import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth.dependencies import require_auth
from backend.citizen_rainfall import router
from services import rainfall_trends as rainfall


class RainfallServiceTests(unittest.TestCase):
    def setUp(self):
        with rainfall._lock:
            rainfall._cache.clear()

    def tearDown(self):
        with rainfall._lock:
            rainfall._cache.clear()

    def test_power_parser_preserves_missing_values_and_date_order(self):
        records = rainfall.parse_power({"properties": {"parameter": {"IMERG_PRECTOT": {
            "20240102": 2.75, "20240101": -999, "20240103": "bad",
        }}}})
        self.assertEqual(records, [
            {"date": "2024-01-01", "rainfall_mm": None},
            {"date": "2024-01-02", "rainfall_mm": 2.75},
            {"date": "2024-01-03", "rainfall_mm": None},
        ])

    def test_aggregation_does_not_treat_missing_as_zero(self):
        daily = [{"date": f"2024-01-{day:02}", "rainfall_mm": float(day)} for day in range(1, 8)]
        weekly = rainfall.aggregate_records(daily, "weekly")
        self.assertEqual(weekly, [{"date": "2024-01-01", "rainfall_mm": 28.0, "coverage_days": 7, "period_days": 7}])
        daily[3]["rainfall_mm"] = None
        weekly = rainfall.aggregate_records(daily, "weekly")
        self.assertIsNone(weekly[0]["rainfall_mm"])
        self.assertEqual(weekly[0]["coverage_days"], 6)

    def test_monthly_aggregation_requires_full_month(self):
        records = [{"date": f"2024-02-{day:02}", "rainfall_mm": 1} for day in range(1, 30)]
        result = rainfall.aggregate_records(records, "monthly")
        self.assertEqual(result[0]["rainfall_mm"], 29)
        self.assertEqual(result[0]["period_days"], 29)
        self.assertEqual(rainfall.aggregate_records(records[:-1], "monthly")[0]["rainfall_mm"], None)

    def test_accumulations_require_complete_recent_windows(self):
        records = [{"date": f"2024-01-{day:02}", "rainfall_mm": 1.25} for day in range(1, 31)]
        summary = rainfall.accumulation_summary(records)
        self.assertEqual(summary["latest_date"], "2024-01-30")
        self.assertEqual(summary["seven_day_mm"], 8.75)
        self.assertEqual(summary["thirty_day_mm"], 37.5)
        records[-2]["rainfall_mm"] = None
        summary = rainfall.accumulation_summary(records)
        self.assertIsNone(summary["seven_day_mm"])
        self.assertIsNone(summary["thirty_day_mm"])
        self.assertEqual(summary["seven_day_coverage"], 6)

    def test_daily_cutoff_and_validation(self):
        start, end = rainfall._date_window(30, today=rainfall.date(2026, 11, 16))
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-07-05", "2026-08-03"))
        for days in (0, 1826, True):
            with self.subTest(days=days), self.assertRaises(ValueError):
                rainfall._date_window(days)

    def test_power_request_uses_daily_utc_grid_source_and_cache(self):
        response = Mock(status_code=200)
        response.json.return_value = {"properties": {"parameter": {"IMERG_PRECTOT": {"20260701": 4.2}}}}
        with patch("services.rainfall_trends.requests.get", return_value=response) as get:
            first = rainfall.fetch_trends(12.42, 75.73, 10)
            second = rainfall.fetch_trends(12.42, 75.73, 10)
        self.assertEqual(first, second)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[0], rainfall.POWER_URL)
        self.assertEqual(get.call_args.kwargs["params"]["parameters"], "IMERG_PRECTOT")
        self.assertEqual(get.call_args.kwargs["params"]["community"], "HY")
        self.assertEqual(get.call_args.kwargs["params"]["time-standard"], "UTC")
        self.assertEqual(get.call_args.kwargs["params"]["longitude"], 75.73)

    def test_power_failures_do_not_fabricate_data_and_are_short_cached(self):
        with patch("services.rainfall_trends.requests.get", side_effect=requests.Timeout("private")) as get:
            with self.assertRaises(rainfall.RainfallUnavailable):
                rainfall.fetch_trends(12, 75)
            cached = rainfall.fetch_trends(12, 75)
        self.assertFalse(cached["available"])
        self.assertEqual(cached["records"], [])
        get.assert_called_once()

    def test_forecast_parsing_and_invalid_values(self):
        records = rainfall.parse_forecast({"data": [
            {"valid_date": "2026-11-17", "precip": 2.34},
            {"valid_date": "2026-11-18", "precip": 0},
        ]})
        self.assertEqual(records[0]["rainfall_mm"], 2.3)
        with self.assertRaises(rainfall.RainfallUnavailable):
            rainfall.parse_forecast({"data": [{"valid_date": "2026-11-17", "precip": None}]})

    def test_forecast_missing_key_never_calls_provider(self):
        with patch.dict("os.environ", {"WEATHERBIT_API_KEY": ""}), patch("services.rainfall_trends.requests.get") as get:
            with self.assertRaises(rainfall.RainfallUnavailable):
                rainfall.fetch_forecast(12, 75)
        get.assert_not_called()

    def test_forecast_failure_sends_no_live_message_or_secret(self):
        response = Mock(status_code=403)
        with patch.dict("os.environ", {"WEATHERBIT_API_KEY": "test-secret"}), patch("services.rainfall_trends.requests.get", return_value=response) as get:
            with self.assertRaises(rainfall.RainfallUnavailable):
                rainfall.fetch_forecast(12, 75)
        self.assertEqual(get.call_args.kwargs["timeout"], (3.05, 8))
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_invalid_coordinates_never_call_providers(self):
        with patch("services.rainfall_trends.requests.get") as get:
            for lat, lon in [(91, 0), (0, 181), (float("nan"), 0)]:
                with self.subTest(lat=lat, lon=lon), self.assertRaises(ValueError):
                    rainfall.fetch_trends(lat, lon)
                with self.subTest(lat=lat, lon=lon), self.assertRaises(ValueError):
                    rainfall.fetch_forecast(lat, lon)
        get.assert_not_called()


class RainfallEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[require_auth] = lambda: {"sub": "test", "role": "Citizen"}
        self.client = TestClient(self.app)

    def test_trends_auth_validation_aggregation_and_headers(self):
        with patch("backend.citizen_rainfall.fetch_trends", return_value={
            "available": True, "records": [{"date": "2024-01-01", "rainfall_mm": 1}], "source": "NASA",
        }) as fetch, patch("backend.citizen_rainfall.aggregate_records", return_value=[{"date": "2024-01-01", "rainfall_mm": 1}]) as aggregate:
            response = self.client.get("/citizen/rainfall/trends?latitude=12&longitude=75&days=365&period=monthly")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, max-age=300")
        fetch.assert_called_once_with(12, 75, 365)
        aggregate.assert_called_once()
        self.assertEqual(response.json()["period"], "monthly")
        self.assertEqual(self.client.get("/citizen/rainfall/trends?latitude=91&longitude=75").status_code, 422)
        self.assertEqual(self.client.get("/citizen/rainfall/trends?latitude=12&longitude=75&period=yearly").status_code, 422)

    def test_unavailable_sources_return_empty_unavailable_contract(self):
        with patch("backend.citizen_rainfall.fetch_trends", side_effect=rainfall.RainfallUnavailable), patch("backend.citizen_rainfall.fetch_forecast", side_effect=rainfall.RainfallUnavailable):
            trends = self.client.get("/citizen/rainfall/trends?latitude=12&longitude=75")
            forecast = self.client.get("/citizen/rainfall/forecast?latitude=12&longitude=75")
        self.assertEqual(trends.json()["records"], [])
        self.assertFalse(trends.json()["available"])
        self.assertFalse(forecast.json()["available"])

    def test_authentication_is_required(self):
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get("/citizen/rainfall/trends?latitude=12&longitude=75").status_code, 401)


if __name__ == "__main__":
    unittest.main()
