"""Regression coverage for confirmed final release audit defects."""
import io
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import BackgroundTasks, HTTPException, UploadFile
from pydantic import ValidationError

import backend_api as api
from backend.auth import jwt_service
from backend.auth.router import TokenRefreshRequest, post_refresh
from landslide_extraction.services import prepare_source, submit_job, MAX_PDF_BYTES
from landslide_extraction.storage import LocalExtractionStorage, job_registry
from landslide_extraction.routes import get_extraction_job, download_extraction_job


class ReleaseSecurityTests(unittest.TestCase):
    def test_guidance_never_labels_a_dangerous_zone_as_a_safe_destination(self):
        from services.safe_route_service import SafeRouteService
        zone = {'type':'Feature','properties':{'name':'Dangerous fixture','risk_level':'CRITICAL'},'geometry':{'type':'Polygon','coordinates':[[[75,12],[76,12],[76,13],[75,13],[75,12]]]}}
        with patch('services.safe_route_service.plan_safe_route') as route:
            result = SafeRouteService().build_guidance(12,75,{'features':[zone]},'HIGH')
        self.assertIsNone(result['safe_zone'])
        self.assertIsNone(result['estimated_direction'])
        self.assertIsNone(result['temporary_shelter'])
        self.assertEqual(result['route']['status'],'no_safe_zone')
        route.assert_not_called()

    def test_location_event_feed_is_admin_only_before_database_query(self):
        from fastapi.testclient import TestClient
        db = Mock()
        db.scalars.return_value.all.return_value = []
        api.app.dependency_overrides[api.get_db] = lambda: db
        try:
            client = TestClient(api.app, base_url='https://testserver')
            self.assertEqual(client.get('/events').status_code, 401)
            with patch('backend.auth.middleware.jwt_service.decode_token', return_value={'sub':'fixture','jti':'fixture','role':'Citizen'}), patch('backend.auth.middleware.is_user_session_active', return_value=True):
                self.assertEqual(client.get('/events', headers={'Authorization':'Bearer fixture'}).status_code, 403)
                db.scalars.assert_not_called()
            with patch('backend.auth.middleware.jwt_service.decode_token', return_value={'sub':'fixture','jti':'fixture','role':'Admin'}), patch('backend.auth.middleware.is_user_session_active', return_value=True):
                self.assertEqual(client.get('/events', headers={'Authorization':'Bearer fixture'}).status_code, 200)
        finally:
            api.app.dependency_overrides.clear()

    def test_environment_is_loaded_before_auth_signing_configuration(self):
        code = '''import os
from unittest.mock import patch
expected = "fixture-signing-key-" + "x" * 40
os.environ.pop("JWT_SECRET", None)
with patch("dotenv.load_dotenv", side_effect=lambda *a, **kw: os.environ.__setitem__("JWT_SECRET", expected)):
    import auth_security
    from backend.auth import jwt_service
    assert jwt_service.JWT_SECRET == expected
'''
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, 'Auth configuration was read before dotenv initialization')

    def test_missing_or_short_production_signing_key_fails_closed(self):
        with patch.dict('os.environ', {'ENVIRONMENT':'production', 'JWT_SECRET':'short'}):
            with self.assertRaises(RuntimeError):
                jwt_service._load_jwt_secret()

    def test_new_real_alerts_are_not_tagged_as_simulations(self):
        rows = [SimpleNamespace(id=1, risk_level='HIGH', message='Live warning', timestamp='2026-10-06T00:00:00Z', delivered_status='real_in_app_pending')]
        db = Mock()
        db.scalars.return_value.all.return_value = rows
        result = api.my_alerts(payload={'sub': 'fixture'}, db=db)
        self.assertIsNone(result['alerts'][0]['source_type'])
        self.assertEqual(result['alerts'][0]['delivery_status'], 'real_in_app_pending')

    def _refresh(self, session):
        payload = {'sub': 'fixture', 'phone': '+911234567890', 'sid': 'sid', 'device': 'device'}
        with patch('backend.auth.router.jwt_service.decode_token', return_value=payload), patch('backend.auth.router.get_user_session_by_id', return_value=session), patch('backend.auth.router.get_user', return_value={'role': 'Citizen'}):
            return post_refresh(TokenRefreshRequest(refresh_token='fixture-refresh'), Mock())

    def test_refresh_rejects_missing_revoked_and_wrong_phone_sessions(self):
        for session in (None, {'revoked_at': 'now'}, {'phone_number': 'wrong', 'token_jti': 'jti'}, {'phone_number': '+911234567890'}):
            with self.subTest(session=session), self.assertRaises(HTTPException) as raised:
                self._refresh(session)
            self.assertEqual(raised.exception.status_code, 401)

    def test_refresh_keeps_session_and_access_jti_for_logout_revocation(self):
        result = self._refresh({'phone_number': '+911234567890', 'token_jti': 'existing-jti', 'revoked_at': None})
        access = jwt_service.decode_token(result['access_token'], 'access')
        refresh = jwt_service.decode_token(result['refresh_token'], 'refresh')
        self.assertEqual(access['jti'], 'existing-jti')
        self.assertEqual(access['sid'], 'sid')
        self.assertEqual(refresh['sid'], 'sid')
        self.assertEqual(access['role'], 'Citizen')

    def test_storage_rejects_traversal_absolute_and_windows_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalExtractionStorage(Path(tmp))
            for name in ('../outside.pdf', '..\\outside.pdf', '/outside.pdf', 'C:\\outside.pdf', 'file.pdf:stream', '..'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    storage.save_source_bytes('job', name, b'fixture')
            self.assertFalse((Path(tmp).parent / 'outside.pdf').exists())
            self.assertEqual(storage.save_source_bytes('job', 'safe.pdf', b'fixture').read_bytes(), b'fixture')

    def test_path_source_cannot_read_outside_configured_root(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'EXTRACTION_SOURCE_DIR': str(Path(tmp) / 'allowed')}):
            secret = Path(tmp) / 'secret.pdf'
            secret.write_bytes(b'fixture')
            with self.assertRaises(HTTPException) as raised:
                prepare_source(path=str(secret))
            self.assertEqual(raised.exception.status_code, 400)

    def test_unapproved_urls_fail_before_network(self):
        with patch.dict('os.environ', {'EXTRACTION_ALLOWED_HOSTS': 'provider.example'}), patch('landslide_extraction.services.requests.get') as get:
            for url in ('http://provider.example/file.pdf', 'https://127.0.0.1/a.pdf', 'https://user:pass@provider.example/a.pdf', 'https://other.example/a.pdf'):
                with self.subTest(url=url), self.assertRaises(HTTPException):
                    prepare_source(url=url)
            get.assert_not_called()

    def test_allowlisted_host_with_private_address_fails_before_network(self):
        with patch.dict('os.environ', {'EXTRACTION_ALLOWED_HOSTS': 'provider.example'}), patch('landslide_extraction.services.socket.getaddrinfo', return_value=[(None, None, None, None, ('127.0.0.1', 443))]), patch('landslide_extraction.services.requests.get') as get:
            with self.assertRaises(HTTPException):
                prepare_source(url='https://provider.example/a.pdf')
            get.assert_not_called()

    def test_oversized_upload_is_rejected(self):
        upload = UploadFile(filename='large.pdf', file=io.BytesIO(b'x' * (MAX_PDF_BYTES + 1)))
        with self.assertRaises(HTTPException) as raised:
            prepare_source(upload=upload)
        self.assertEqual(raised.exception.status_code, 413)

    def test_job_status_and_download_do_not_disclose_another_users_job(self):
        job_registry.create('release-owner-test', 'safe.pdf', 'fixture', owner_id='user-a')
        for payload in ({'sub': 'user-b'}, {}):
            for endpoint in (get_extraction_job, download_extraction_job):
                with self.subTest(payload=payload, endpoint=endpoint), self.assertRaises(HTTPException) as raised:
                    endpoint('release-owner-test', payload)
                self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(get_extraction_job('release-owner-test', {'sub': 'user-a'}).status, 'queued')

    def test_prediction_rejects_invalid_coordinates_features_and_models(self):
        body = dict(latitude=12, longitude=75, deformation_mm=5, velocity_mm_yr=12, coherence=.8, slope_deg=24, soil_moisture_pct=45)
        for key, value in [('latitude', 91), ('longitude', -181), ('latitude', float('nan')), ('deformation_mm', float('inf')), ('coherence', 2), ('slope_deg', -1), ('soil_moisture_pct', 101), ('ndvi', 2), ('model', 'unknown')]:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                api.PredictRequest(**{**body, key: value})
        for model in (api.LocationUpdateRequest, api.ProtectedLocationUpdateRequest):
            with self.assertRaises(ValidationError):
                model(user_id='fixture', latitude=91, longitude=75)

    def test_admin_simulation_never_overrides_live_citizen_location_or_risk(self):
        req = api.LocationUpdateRequest(user_id='fixture', latitude=12, longitude=75)
        simulation = Mock()
        simulation.read_state.return_value = {'enabled': True, 'forced_risk': 'CRITICAL'}
        simulation.apply_location_override.return_value = {'latitude': 40, 'longitude': 50}
        weather = Mock()
        weather.fetch_weather_context.return_value = {}
        weather.fetch_rainfall_mm.return_value = {'rainfall_mm': 0}
        with patch.object(api, 'simulation_mode', simulation), patch.object(api, 'weather_service', weather), patch.object(api, 'predict', return_value={'risk_label': 'Low', 'confidence': .9}), patch.object(api, 'load_zones', return_value={'features': []}), patch.object(api, 'safe_route_service', Mock(build_guidance=Mock(return_value={}))), patch.object(api, 'save_event') as save, patch.object(api, 'process_reading') as alert:
            result = api._evaluate_location(req, BackgroundTasks(), None, False)
        self.assertEqual(result['location'], {'latitude': 12.0, 'longitude': 75.0, 'source': 'live'})
        self.assertEqual(result['final_risk'], 'LOW')
        self.assertFalse(result['simulation']['enabled'])
        simulation.apply_location_override.assert_not_called()
        simulation.effective_forced_risk.assert_not_called()
        save.assert_called_once()
        alert.assert_not_called()
        weather.fetch_weather_context.assert_called_once_with(12.0, 75.0)
