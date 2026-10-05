"""Isolated SMAP fixtures; never runtime environmental defaults."""
import io
import json
import logging
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import h5py
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.auth.dependencies import require_auth
from backend.citizen_environment import router
from services.smap_environment import SmapService, SmapUnavailable, parse_granule, select_observation, _download

NOW = datetime.now(timezone.utc)
URL = "https://data.nsidc.earthdatacloud.nasa.gov/nsidc-cumulus-prod-protected/SMAP/SPL2SMP_NRT/107/2026/01/01/SMAP_L2_SM_P_NRT_TEST.h5"
ENTRY = {"title": "test", "time_start": NOW.isoformat(), "links": [{"rel": "http://esipfed.org/ns/fedsearch/1.1/data#", "href": URL}]}


def fixture(**changes):
    fields = {"latitude": [12.1], "longitude": [75.1], "EASE_row_index": [160], "EASE_column_index": [680],
              "soil_moisture": [0.17257299], "retrieval_qual_flag": [0], "surface_flag": [0],
              "surface_temperature": [299.0], "grid_surface_status": [0],
              "tb_time_utc": [NOW.isoformat().encode()]}
    fields.update(changes)
    buffer = io.BytesIO()
    with h5py.File(buffer, "w") as file:
        group = file.create_group("Soil_Moisture_Retrieval_Data")
        for name, values in fields.items():
            group.create_dataset(name, data=values)
        group["soil_moisture"].attrs.update({"units": "cm**3/cm**3", "_FillValue": -9999., "valid_min": 0.02, "valid_max": 0.5})
        group["surface_temperature"].attrs["_FillValue"] = -9999.
        file.create_group("Metadata/GridSpatialRepresentation").attrs["resolution"] = 36.
    return buffer.getvalue()


class SmapQualityTests(unittest.TestCase):
    def result(self, **changes):
        return select_observation(parse_granule(fixture(**changes)), 12, 75, "test.h5", NOW)

    def test_valid_retrieval_and_correct_conversion(self):
        result = self.result()
        self.assertAlmostEqual(result["soil_moisture_percent"], 17.257299)
        self.assertEqual(result["native_unit"], "cm**3/cm**3")
        self.assertEqual(result["grid"]["row"], 160)
        self.assertEqual(result["unit"], "% water by volume")

    def test_quality_zero_accepted(self):
        self.assertIsNotNone(self.result(retrieval_qual_flag=[0]))

    def test_quality_eight_accepted_with_documented_low_latitude_freeze_check(self):
        self.assertIsNotNone(self.result(retrieval_qual_flag=[8], surface_flag=[128]))

    def test_quality_nine_rejected(self):
        self.assertIsNone(self.result(retrieval_qual_flag=[9]))

    def test_sentinel_nonfinite_and_out_of_range_rejected(self):
        for value in [-9999, float("nan"), float("inf"), -1, 0, 0.019, 0.501]:
            with self.subTest(value=value):
                self.assertIsNone(self.result(soil_moisture=[value]))

    def test_surface_urban_frozen_unsupported_and_missing_flags_rejected(self):
        for flag in [8, 136, 256, 16, 65534]:
            with self.subTest(flag=flag):
                self.assertIsNone(self.result(surface_flag=[flag]))
        for temperature in [270, 273.15, -9999, float("nan"), 351]:
            self.assertIsNone(self.result(surface_temperature=[temperature]))
        self.assertIsNone(self.result(grid_surface_status=[1]))

    def test_radiometer_freeze_exception_is_not_applied_at_high_latitude(self):
        parsed = parse_granule(fixture(latitude=[50.1], longitude=[75.1], surface_flag=[128], retrieval_qual_flag=[8]))
        self.assertIsNone(select_observation(parsed, 50, 75, "test.h5", NOW))

    def test_missing_old_future_and_naive_timestamps_rejected(self):
        for timestamp in ["", "bad", (NOW-timedelta(hours=73)).isoformat(), (NOW+timedelta(hours=1)).isoformat(), NOW.replace(tzinfo=None).isoformat()]:
            self.assertIsNone(self.result(tb_time_utc=[timestamp.encode()]))

    def test_no_distant_substitution(self):
        self.assertIsNone(self.result(latitude=[15.]))

    def test_nearest_valid_selected_without_averaging_invalid_pixel(self):
        changes = {"latitude": [12., 12.2, 12.3], "longitude": [75., 75., 75.],
                   "EASE_row_index": [160, 159, 158], "EASE_column_index": [680]*3,
                   "soil_moisture": [0.4, 0.2, 0.3], "retrieval_qual_flag": [9, 0, 8], "surface_flag": [8, 0, 0],
                   "surface_temperature": [299.]*3, "grid_surface_status": [0]*3, "tb_time_utc": [NOW.isoformat().encode()]*3}
        result = self.result(**changes)
        self.assertEqual(result["native_value"], 0.2)
        self.assertEqual(result["grid"]["row"], 159)

    def test_malformed_hdf_and_unsupported_units_rejected(self):
        with self.assertRaises(SmapUnavailable):
            parse_granule(b"not HDF5")
        data = io.BytesIO(fixture())
        with h5py.File(data, "r+") as file:
            file["Soil_Moisture_Retrieval_Data/soil_moisture"].attrs["units"] = "percent saturation"
        with self.assertRaises(SmapUnavailable):
            parse_granule(data.getvalue())


class SmapAccessTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"EARTHDATA_TOKEN": "test-private-token"})
        env.start(); self.addCleanup(env.stop)
        self.service = SmapService()
        read = patch("services.smap_environment._read", return_value=json.dumps({"feed": {"entry": [ENTRY]}}).encode())
        self.read = read.start(); self.addCleanup(read.stop)
        download = patch("services.smap_environment._download", return_value=fixture())
        self.download = download.start(); self.addCleanup(download.stop)

    def test_valid_coordinates_dynamic_discovery_and_cache(self):
        result = self.service.fetch(12, 75)
        self.assertEqual(result["source"], "NASA SMAP NRT")
        self.service.fetch(12.001, 75.001)
        self.read.assert_called_once(); self.download.assert_called_once()
        self.assertIn("circle=75.0%2C12.0%2C100000", self.read.call_args.args[0])

    def test_invalid_coordinates_rejected_before_network(self):
        for coordinates in [(91, 0), (0, 181), (None, 1), (True, 1), (float("nan"), 1)]:
            with self.assertRaises(SmapUnavailable): self.service.fetch(*coordinates)
        self.read.assert_not_called()

    def test_missing_token_rejected(self):
        with patch.dict("os.environ", {"EARTHDATA_TOKEN": ""}), self.assertRaises(SmapUnavailable):
            self.service.fetch(12, 75)
        self.read.assert_not_called()

    def test_authentication_failure_sanitized_and_negative_cached(self):
        self.download.side_effect = HTTPError(URL, 401, "test-private-token", {}, None)
        with self.assertRaisesRegex(SmapUnavailable, r"^Live data unavailable\.$"):
            self.service.fetch(12, 75)
        with self.assertRaises(SmapUnavailable): self.service.fetch(12, 75)
        self.download.assert_called_once()

    def test_nasa_failure_timeout_and_malformed_catalogue(self):
        for error in [TimeoutError("test-private-token"), ValueError("test-private-token"), OSError("test-private-token")]:
            self.read.side_effect = error
            with self.assertRaisesRegex(SmapUnavailable, r"^Live data unavailable\.$"):
                SmapService().fetch(12, 75)

    def test_no_valid_retrieval_has_no_fallback(self):
        self.download.return_value = fixture(retrieval_qual_flag=[9])
        with self.assertRaises(SmapUnavailable): self.service.fetch(12, 75)

    def test_token_not_in_response_or_logging(self):
        with patch.object(logging.Logger, "_log") as log:
            self.assertNotIn("test-private-token", json.dumps(self.service.fetch(12, 75)))
            log.assert_not_called()

    def test_signed_delivery_never_receives_bearer_token(self):
        self.read.side_effect = [HTTPError(URL, 303, "", {"Location": "https://d123.cloudfront.net/path/SMAP_L2_SM_P_NRT_TEST.h5?Signature=secret"}, None), b"data"]
        self.assertEqual(_download(URL, "test-private-token", 999999999), b"data")
        self.assertEqual(self.read.call_args_list[0].args[2], "test-private-token")
        self.assertEqual(len(self.read.call_args_list[1].args), 2)

    def test_untrusted_delivery_and_download_hosts_rejected(self):
        with self.assertRaises(SmapUnavailable): _download("https://example.com/test.h5", "secret", 999999999)
        self.read.side_effect = HTTPError(URL, 303, "", {"Location": "https://example.com/test.h5"}, None)
        with self.assertRaises(SmapUnavailable): _download(URL, "secret", 999999999)


class EnvironmentEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI(); self.app.include_router(router)
        self.app.dependency_overrides[require_auth] = lambda: {"sub": "fixture", "role": "Citizen"}
        self.client = TestClient(self.app)
        fetch = patch("backend.citizen_environment.smap_service.fetch", return_value={"source": "NASA SMAP NRT"})
        self.fetch = fetch.start(); self.addCleanup(fetch.stop)

    def test_valid_coordinates(self):
        result = self.client.get("/citizen/environment/current?latitude=12&longitude=75")
        self.assertEqual(result.status_code, 200); self.fetch.assert_called_once_with(12, 75)
        self.assertEqual(result.headers["cache-control"], "no-store")

    def test_invalid_latitude(self):
        for value in ["91", "nan", "inf", "bad"]:
            self.assertEqual(self.client.get(f"/citizen/environment/current?latitude={value}&longitude=75").status_code, 422)
        self.fetch.assert_not_called()

    def test_invalid_longitude(self):
        for value in ["181", "nan", "inf", "bad"]:
            self.assertEqual(self.client.get(f"/citizen/environment/current?latitude=12&longitude={value}").status_code, 422)
        self.fetch.assert_not_called()

    def test_missing_coordinates(self):
        for query in ["", "?latitude=12", "?longitude=75"]:
            self.assertEqual(self.client.get("/citizen/environment/current"+query).status_code, 422)
        self.fetch.assert_not_called()

    def test_unavailable_clean_no_secret(self):
        self.fetch.side_effect = SmapUnavailable()
        result = self.client.get("/citizen/environment/current?latitude=12&longitude=75")
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json(), {"detail": "Live data unavailable."})

    def test_authentication_required(self):
        self.app.dependency_overrides.clear()
        with patch("backend.auth.dependencies.authenticate_profile", side_effect=HTTPException(status_code=401, detail="Unauthorized")):
            self.assertEqual(self.client.get("/citizen/environment/current?latitude=12&longitude=75").status_code, 401)
        self.fetch.assert_not_called()

    def test_registered_endpoint_and_ml_isolation(self):
        import backend_api
        self.assertIn("/citizen/environment/current", backend_api.app.openapi()["paths"])
        self.assertEqual(backend_api.ProtectedLocationUpdateRequest(latitude=12, longitude=75).soil_moisture_pct, 45.)
        source = (Path(__file__).resolve().parents[1]/"web-ui/src/pages/Public.jsx").read_text(encoding="utf-8")
        prediction = source.split("const tryPredict =", 1)[1].split("const evaluatePosition =", 1)[0]
        self.assertIn("soil_moisture_pct: 45.0", prediction)
        self.assertNotIn("soilObservation", prediction)

    def test_environment_endpoint_never_calls_ml_weather_routing_or_database(self):
        import backend_api
        with patch.object(backend_api, "predict", side_effect=AssertionError("ML called")), \
             patch.object(backend_api, "store_location", side_effect=AssertionError("database called")), \
             patch("services.weather_extension.WeatherExtensionService.fetch_weather_context", side_effect=AssertionError("weather called")), \
             patch.object(backend_api, "plan_safe_route", side_effect=AssertionError("routing called")):
            self.assertEqual(self.client.get("/citizen/environment/current?latitude=12&longitude=75").status_code, 200)

    def test_predict_risk_keeps_existing_feature_value_and_never_calls_smap(self):
        import backend_api
        req = backend_api.PredictRequest(latitude=12, longitude=75, deformation_mm=5., velocity_mm_yr=12.,
                                        coherence=0.8, slope_deg=24., soil_moisture_pct=45.)
        with patch.object(backend_api, "predict", return_value={"risk_label": "LOW"}) as predict, \
             patch("services.weather_extension.WeatherExtensionService.fetch_weather_context", return_value={}), \
             patch("services.weather_extension.WeatherExtensionService.fetch_rainfall_mm", return_value={"rainfall_mm": 3}), \
             patch.object(backend_api, "load_zones", return_value={}), \
             patch.object(backend_api, "find_zone_matches", return_value=[]), \
             patch.object(backend_api, "highest_zone_risk", return_value="LOW"), \
             patch("services.safe_route_service.SafeRouteService.build_guidance", return_value={}), \
             patch("services.smap_environment.smap_service.fetch", side_effect=AssertionError("SMAP entered ML")):
            backend_api.predict_risk(req, {})
            self.assertEqual(predict.call_args.kwargs["soil_moisture_pct"], 45.)
            self.assertEqual(predict.call_args.kwargs["rainfall_mm"], 3)

    def test_existing_rf_xgb_and_ensemble_inference_preserve_inputs(self):
        from predict import predict
        for model in ["random_forest", "xgboost", "ensemble"]:
            result = predict(deformation_mm=5., velocity_mm_yr=12., coherence=0.8, rainfall_mm=3.,
                             slope_deg=24., soil_moisture_pct=45., model=model)
            self.assertEqual(result["feature_values"]["soil_moisture_pct"], 45.)
            self.assertAlmostEqual(sum(result["probabilities"].values()), 1., places=5)
