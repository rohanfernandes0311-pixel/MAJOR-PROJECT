"""Exercise the isolated demo without importing runtime database initialization."""
from io import BytesIO
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.auth.middleware import get_current_user
from geofencing import point_in_polygon
from services.httpsms_export import HEADERS, normalize_phone
from services.simulation_demonstration import CONFIG, router
from services.simulation_route import segment_enters_danger, boundary_distance


class SimulationDemonstrationTests(TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)
        self.app.dependency_overrides[get_current_user] = lambda: {'role': 'Admin'}
        env = patch.dict('os.environ', {'HTTPSMS_FROM_NUMBER': '+919876543210'})
        env.start()
        self.addCleanup(env.stop)

    def test_every_location_and_risk_geofence_route_and_workbook(self):
        for location in CONFIG['locations']:
            for risk in CONFIG['risk_levels']:
                with self.subTest(location=location, risk=risk):
                    response = self.client.get('/admin/simulation/visual/scenario', params={'location': location, 'risk': risk})
                    self.assertEqual(response.status_code, 200)
                    demo = response.json()
                    ring = demo['dangerZone']['geometry']['coordinates'][0]
                    inside = [p for p in demo['people'] if point_in_polygon(p['latitude'], p['longitude'], ring)]
                    outside = [p for p in demo['people'] if not p['inside']]
                    self.assertEqual(len(inside), 4)
                    self.assertEqual(len(outside), 4)
                    self.assertLessEqual(len(demo['people']), 10)
                    self.assertIn(location, demo['message'])
                    self.assertIn(risk.lower(), demo['message'])
                    self.assertIn('Do not return', demo['message'])
                    self.assertTrue(all(normalize_phone(p['phone']) is None for p in demo['people']))
                    path = demo['route']['route']['path']
                    self.assertTrue(point_in_polygon(path[0]['latitude'], path[0]['longitude'], ring))
                    route_info = demo['route']['route']
                    self.assertGreaterEqual(route_info['boundary_distance_meters'], 300)
                    self.assertLessEqual(route_info['boundary_distance_meters'], 1000)
                    self.assertLess(route_info['distance_meters'], 2200)
                    self.assertEqual(route_info['candidate_total'], 3)
                    self.assertTrue(route_info['osm_way_ids'])
                    self.assertGreater(route_info['estimated_minutes'], 0)
                    self.assertAlmostEqual(path[0]['latitude'], sum(p['latitude'] for p in inside) / len(inside), places=8)
                    self.assertAlmostEqual(path[0]['longitude'], sum(p['longitude'] for p in inside) / len(inside), places=8)
                    exit_point = path[route_info['exit_index']]
                    self.assertLess(boundary_distance(exit_point, ring), .01)
                    # The first leg exits at the exact boundary. Entire subsequent
                    # segments must be outside, not just their endpoints.
                    for start, end in zip(path[route_info['exit_index']:], path[route_info['exit_index']+1:]):
                        self.assertFalse(segment_enters_danger(start, end, ring))
                    safe_ring = demo['safeZone']['geometry']['coordinates'][0]
                    self.assertTrue(all(not point_in_polygon(lat,lon,ring) for lon,lat in safe_ring))
                    self.assertTrue(point_in_polygon(path[-1]['latitude'], path[-1]['longitude'], safe_ring))
                    export = self.client.post('/admin/simulation/visual/excel', json={'location': location, 'risk': risk, 'message': demo['message'], 'recipient_ids': [p['displayId'] for p in inside]})
                    self.assertEqual(export.status_code, 200, export.text if export.status_code != 200 else '')
                    workbook = load_workbook(BytesIO(export.content))
                    sheet = workbook.active
                    rows = list(sheet.values)
                    self.assertEqual(tuple(rows[0]), HEADERS)
                    self.assertEqual(len(rows), 5)
                    self.assertEqual({row[1] for row in rows[1:]}, {p['phone'] for p in inside})
                    self.assertTrue({row[1] for row in rows[1:]}.isdisjoint({p['phone'] for p in outside}))
                    self.assertTrue(all(row[0] == '+919876543210' and row[2] == demo['message'] and row[3] is None for row in rows[1:]))
                    self.assertIn(f'LandSense_{location}_{risk}_SMS_', export.headers['content-disposition'])
                    workbook.close()

    def test_admin_only(self):
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get('/admin/simulation/visual/scenario').status_code, 401)
        self.app.dependency_overrides[get_current_user] = lambda: {'role': 'Citizen'}
        self.assertEqual(self.client.get('/admin/simulation/visual/scenario').status_code, 403)
        self.assertEqual(self.client.post('/admin/simulation/visual/excel', json={'location': 'Madikeri', 'risk': 'HIGH', 'message': 'Demo'}).status_code, 403)

    def test_invalid_inputs_missing_sender_and_formula_text(self):
        self.assertEqual(self.client.get('/admin/simulation/visual/scenario?location=Unknown').status_code, 422)
        self.assertEqual(self.client.get('/admin/simulation/visual/scenario?risk=LOW').status_code, 422)
        request = {'location': 'Madikeri', 'risk': 'HIGH', 'message': ' '}
        self.assertEqual(self.client.post('/admin/simulation/visual/excel', json=request).status_code, 422)
        request['recipient_ids'] = [p['displayId'] for p in self.client.get('/admin/simulation/visual/scenario').json()['people'] if p['inside']]
        request['message'] = '=HYPERLINK("https://example.com")'
        response = self.client.post('/admin/simulation/visual/excel', json=request)
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook.active['C2'].data_type, 's')
        self.assertTrue(workbook.active['C2'].value.startswith('SIMULATION ONLY'))
        workbook.close()
        with patch.dict('os.environ', {'HTTPSMS_FROM_NUMBER': ''}):
            self.assertEqual(self.client.post('/admin/simulation/visual/excel', json=request).status_code, 422)
