from __future__ import annotations

import unittest
from unittest.mock import patch

import backend_api
from route_planner import plan_safe_route, zone_risk_at


WAYANAD_ZONE = {
    "type": "Feature",
    "properties": {"zone_id": "WYD-03", "name": "Wayanad Critical Scar", "risk_level": "HIGH"},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[76.06, 11.53], [76.18, 11.53], [76.18, 11.66], [76.06, 11.66], [76.06, 11.53]]],
    },
}


class SafeRouteGuidanceTests(unittest.TestCase):
    def test_route_uses_exact_current_location_and_user_destination(self) -> None:
        zones = {"type": "FeatureCollection", "features": [WAYANAD_ZONE]}
        result = plan_safe_route(11.58, 76.12, 11.70, 76.20, zones)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["path"][0], {"latitude": 11.58, "longitude": 76.12})
        self.assertEqual(result["path"][-1], {"latitude": 11.70, "longitude": 76.20})
        self.assertGreater(result["distance_km"], 0)
        self.assertEqual(zone_risk_at(11.70, 76.20, zones), "LOW")
        risk_samples = [zone_risk_at(point["latitude"], point["longitude"], zones) for point in result["path"]]
        self.assertIn("HIGH", risk_samples)  # The Citizen starts inside the configured zone.
        self.assertLess(risk_samples.count("HIGH"), len(risk_samples))

    def test_dynamic_grid_reaches_destinations_beyond_the_original_local_window(self) -> None:
        result = plan_safe_route(11.58, 76.12, 12.20, 76.80, {"type": "FeatureCollection", "features": []})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["path"][0], {"latitude": 11.58, "longitude": 76.12})
        self.assertEqual(result["path"][-1], {"latitude": 12.20, "longitude": 76.80})

    def test_existing_route_endpoint_remains_authenticated_and_geojson_authoritative(self) -> None:
        request = backend_api.RouteRequest(start_latitude=11.58, start_longitude=76.12, end_latitude=11.70, end_longitude=76.20)
        zones = {"type": "FeatureCollection", "features": [WAYANAD_ZONE]}
        with patch.object(backend_api, "load_zones", return_value=zones) as loader:
            result = backend_api.route_safe(request, {"sub": "citizen"})
        loader.assert_called_once_with(backend_api.ZONE_PATH)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["path"][-1], {"latitude": 11.70, "longitude": 76.20})

    def test_route_coordinates_are_validated(self) -> None:
        for field, value in (("start_latitude", 91), ("start_longitude", 181), ("end_latitude", -91), ("end_longitude", -181)):
            payload = {"start_latitude": 11.58, "start_longitude": 76.12, "end_latitude": 11.70, "end_longitude": 76.20, field: value}
            with self.subTest(field=field), self.assertRaises(Exception):
                backend_api.RouteRequest(**payload)


if __name__ == "__main__":
    unittest.main()
