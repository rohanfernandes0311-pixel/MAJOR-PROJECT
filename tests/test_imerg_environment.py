"""Test-only HDF5 measurements; production never uses these fixtures."""
import io
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import h5py
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.auth.dependencies import require_auth
from backend.citizen_environment import router
from services.imerg_environment import ImergService, ImergUnavailable, parse_granule, select_observation, _download, _read

NOW = datetime.now(timezone.utc)
START = (NOW-timedelta(hours=4)).replace(minute=0, second=0, microsecond=0)
END = START+timedelta(minutes=30)-timedelta(seconds=1)
GRANULE = f'3B-HHR-E.MS.MRG.3IMERG.{START:%Y%m%d}-S{START:%H%M%S}-E{END:%H%M%S}.0000.V07C.HDF5'
URL = 'https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3/GPM_3IMERGHHE.07/2026/278/'+GRANULE
ENTRY = {'time_start': START.isoformat(), 'time_end': END.isoformat(),
         'links': [{'rel': 'http://esipfed.org/ns/fedsearch/1.1/data#', 'href': URL}]}


def fixture(rate=0.25, quality=0.8, error=0.1, unit='mm/hr', empty='NOT_EMPTY', missing=None):
    buffer = io.BytesIO()
    with h5py.File(buffer, 'w') as file:
        file.attrs['FileHeader'] = f'EmptyGranule={empty};StartGranuleDateTime={START.isoformat()};StopGranuleDateTime={END.isoformat()};'
        g = file.create_group('Grid')
        g['lat'] = np.array([12.95, 13.05], dtype='f4')
        g['lon'] = np.array([77.55, 77.65, 77.75], dtype='f4')
        for name, value in [('precipitation', rate), ('precipitationQualityIndex', quality), ('randomError', error)]:
            if name == missing: continue
            d = g.create_dataset(name, data=np.full((1, 3, 2), value, dtype='f4'))
            d.attrs['units'] = unit if name != 'precipitationQualityIndex' else '1'
            d.attrs['_FillValue'] = -9999.9
    return buffer.getvalue()


class ImergMeasurementTests(unittest.TestCase):
    def result(self, **kwargs):
        return select_observation(parse_granule(fixture(**kwargs)), 12.9716, 77.5946, GRANULE, NOW)

    def test_real_rate_is_not_converted_to_accumulation(self):
        r = self.result(); self.assertAlmostEqual(r['precipitation_rate'], 0.25)
        self.assertEqual(r['unit'], 'mm/h'); self.assertEqual(r['interval_minutes'], 30)
        self.assertEqual(r['source'], 'NASA GPM IMERG Early')

    def test_verified_zero_is_a_measurement(self):
        self.assertEqual(self.result(rate=0)['precipitation_rate'], 0)

    def test_nasa_not_empty_metadata_accepted(self):
        self.assertEqual(self.result(empty='NOT_EMPTY')['precipitation_rate'], 0.25)

    def test_empty_and_invalid_metadata_rejected(self):
        for value in ['EMPTY', '', 'NOTEMPTY', 'UNKNOWN', 'NOT_EMPTY_EXTRA']:
            with self.subTest(value=value), self.assertRaises(ImergUnavailable):
                self.result(empty=value)

    def test_missing_empty_granule_metadata_rejected(self):
        buffer = io.BytesIO(fixture())
        with h5py.File(buffer, 'r+') as file:
            header = file.attrs['FileHeader'].replace('EmptyGranule=NOT_EMPTY;', '')
            file.attrs['FileHeader'] = header
        with self.assertRaises(ImergUnavailable): parse_granule(buffer.getvalue())

    def test_missing_file_header_rejected_safely_by_service(self):
        buffer = io.BytesIO(fixture())
        with h5py.File(buffer, 'r+') as file: del file.attrs['FileHeader']
        service = ImergService()
        with patch.dict('os.environ', {'EARTHDATA_TOKEN': 'test-private-token'}), \
             patch.object(service, '_catalog', return_value=ENTRY), \
             patch('services.imerg_environment._download', return_value=buffer.getvalue()), \
             self.assertRaisesRegex(ImergUnavailable, r'^Live data unavailable\.$'):
            service.fetch(12.97, 77.59)

    def test_grid_selection_uses_native_coordinates_and_correct_axis_order(self):
        g = parse_granule(fixture()); g['precipitation'][0][2, 1] = 1.25
        r = select_observation(g, 13.04, 77.74, GRANULE, NOW)
        self.assertEqual((r['grid']['row'], r['grid']['column']), (1, 2))
        self.assertEqual(r['precipitation_rate'], 1.25)
        self.assertEqual(r['spatial_resolution_degrees'], 0.1)
        self.assertAlmostEqual(r['grid']['latitude'], 13.05, places=4)

    def test_invalid_sentinel_and_nonfinite_rates(self):
        for rate in [-9999, -9999.9, -1, float('nan'), float('inf'), 200.1]:
            with self.subTest(rate=rate), self.assertRaises(ImergUnavailable): self.result(rate=rate)

    def test_missing_or_lowest_quality_is_rejected(self):
        for quality in [-9999.9, float('nan'), 0, -1, 1.1]:
            with self.subTest(quality=quality), self.assertRaises(ImergUnavailable): self.result(quality=quality)

    def test_missing_or_invalid_uncertainty_rejected(self):
        for error in [-9999.9, float('nan'), 1001]:
            with self.subTest(error=error), self.assertRaises(ImergUnavailable): self.result(error=error)

    def test_native_units_required(self):
        for unit in ['mm', 'inch/hr', 'unknown']:
            with self.subTest(unit=unit), self.assertRaises(ImergUnavailable): self.result(unit=unit)

    def test_missing_dataset_and_empty_granule_rejected(self):
        with self.assertRaises(KeyError): parse_granule(fixture(missing='precipitation'))
        with self.assertRaises(ImergUnavailable): self.result(empty='EMPTY')
        with self.assertRaises(ImergUnavailable): parse_granule(b'not hdf5')

    def test_stale_future_and_outside_grid_rejected(self):
        g = parse_granule(fixture())
        for now, lat in [(START+timedelta(hours=13), 12.97), (START-timedelta(hours=1), 12.97), (NOW, 15)]:
            with self.assertRaises(ImergUnavailable): select_observation(g, lat, 77.59, GRANULE, now)

    def test_bad_pixel_never_replaced_by_neighbour(self):
        g = parse_granule(fixture()); g['precipitation'][0][0, 0] = -9999.9
        with self.assertRaises(ImergUnavailable): select_observation(g, 12.97, 77.59, GRANULE, NOW)

    def test_grid_spacing_and_dimensions_validated(self):
        b = io.BytesIO(fixture())
        with h5py.File(b, 'r+') as f: f['Grid/lat'][1] = 14
        with self.assertRaises(ImergUnavailable): parse_granule(b.getvalue())


class ImergRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.service = ImergService()
        for p in [patch.dict('os.environ', {'EARTHDATA_TOKEN': 'test-private-token'}),
                  patch.object(self.service, '_catalog', return_value=ENTRY),
                  patch('services.imerg_environment._download', return_value=fixture())]:
            result = p.start(); self.addCleanup(p.stop)
            if hasattr(result, 'assert_called'): setattr(self, 'catalog' if not hasattr(self, 'catalog') else 'download', result)

    def test_cached_global_grid_reused_across_gps_coordinates(self):
        self.service.fetch(12.97, 77.59); self.service.fetch(13.04, 77.74)
        self.catalog.assert_called_once(); self.download.assert_called_once()

    def test_catalog_refresh_does_not_redownload_same_granule(self):
        self.service.fetch(12.97, 77.59); self.service._catalog_until = 0
        self.service.fetch(12.97, 77.59)
        self.assertEqual(self.catalog.call_count, 2); self.download.assert_called_once()

    def test_concurrent_requests_download_and_parse_once(self):
        with patch('services.imerg_environment.parse_granule', wraps=parse_granule) as parse:
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: self.service.fetch(12.97, 77.59), range(8)))
            self.assertEqual(len(results), 8); parse.assert_called_once(); self.download.assert_called_once()

    def test_failures_sanitized_and_backed_off(self):
        for error in [PermissionError('test-private-token:403 EULA'), TimeoutError('test-private-token'), ValueError('malformed')]:
            self.service._failure_until = 0; self.download.side_effect = error
            with self.assertRaisesRegex(ImergUnavailable, r'^Live data unavailable\.$'): self.service.fetch(12.97, 77.59)
            count = self.download.call_count
            with self.assertRaises(ImergUnavailable): self.service.fetch(12.97, 77.59)
            self.assertEqual(self.download.call_count, count)

    def test_missing_token_never_downloads(self):
        with patch.dict('os.environ', {'EARTHDATA_TOKEN': ''}), self.assertRaises(ImergUnavailable): self.service.fetch(12.97, 77.59)
        self.download.assert_not_called()

    def test_invalid_coordinates_never_access_nasa(self):
        for lat, lon in [(91, 0), (0, 181), (float('nan'), 0), (0, float('inf'))]:
            with self.assertRaises(ImergUnavailable): self.service.fetch(lat, lon)
        self.catalog.assert_not_called()

    def test_catalog_missing_and_timestamp_mismatch_fail_closed(self):
        for entry in [{}, {**ENTRY, 'time_start': (START-timedelta(hours=1)).isoformat()}]:
            self.catalog.return_value = entry; self.service._failure_until = 0; self.service._catalog_until = 0
            with self.assertRaises(ImergUnavailable): self.service.fetch(12.97, 77.59)

    def test_response_has_no_credentials_or_prediction_feature(self):
        r = self.service.fetch(12.97, 77.59)
        self.assertNotIn('test-private-token', json.dumps(r)); self.assertNotIn('rainfall_mm', r)

    def test_untrusted_download_url_rejected_before_token_sent(self):
        for url in ['https://example.com/'+GRANULE, URL+'?secret=x', URL.replace('3B-HHR-E', '3B-HHR-L')]:
            with self.assertRaises(ImergUnavailable): _download(url, 'test-private-token', 9999999999)

    def test_signed_delivery_never_receives_token(self):
        from unittest.mock import MagicMock
        first, second = MagicMock(), MagicMock()
        first.status_code = 303; first.headers = {'Location': 'https://d123.cloudfront.net/path/'+GRANULE+'?Signature=test-secret'}
        second.status_code = 200; second.iter_content.return_value = [b'content']
        first.__enter__.return_value = first; second.__enter__.return_value = second
        with patch('services.imerg_environment.requests.get', side_effect=[first, second]) as get:
            self.assertEqual(_read(URL, 9999999999, 'test-private-token'), b'content')
            self.assertEqual(get.call_args_list[0].kwargs['headers'], {'Authorization': 'Bearer test-private-token'})
            self.assertEqual(get.call_args_list[1].kwargs['headers'], {})

    def test_nasa_http_authentication_and_service_failures_rejected(self):
        from unittest.mock import MagicMock
        for status in [401, 403, 404, 500, 503]:
            response = MagicMock(); response.__enter__.return_value = response
            response.status_code = status
            with patch('services.imerg_environment.requests.get', return_value=response), self.assertRaises(ImergUnavailable):
                _read(URL, 9999999999, 'test-private-token')
            response.iter_content.assert_not_called()

    def test_catalog_is_early_v07_recent_and_has_no_credentials(self):
        from services.imerg_environment import CMR_URL
        from urllib.parse import parse_qs, urlparse
        with patch('services.imerg_environment._read', return_value=json.dumps({'feed': {'entry': [ENTRY]}}).encode()) as read:
            self.assertEqual(ImergService()._catalog(NOW, 9999999999), ENTRY)
            url = read.call_args.args[0]
            self.assertTrue(url.startswith(CMR_URL))
            params = parse_qs(urlparse(url).query)
            self.assertEqual(params['short_name'], ['GPM_3IMERGHHE'])
            self.assertEqual(params['version'], ['07']); self.assertEqual(params['sort_key'], ['-start_date'])
            self.assertNotIn('test-private-token', url)
        with patch('services.imerg_environment._read', return_value=b'{"feed":{"entry":[]}}'), self.assertRaises(ImergUnavailable):
            ImergService()._catalog(NOW, 9999999999)

    def test_download_size_limit_and_untrusted_redirect(self):
        from unittest.mock import MagicMock
        response = MagicMock(); response.__enter__.return_value = response
        response.status_code = 200; response.iter_content.return_value = [b'too large']
        with patch('services.imerg_environment.requests.get', return_value=response), self.assertRaises(ImergUnavailable):
            _read(URL, 9999999999, 'test-private-token', limit=2)
        response.status_code = 303; response.headers = {'Location': 'https://example.com/'+GRANULE}
        with patch('services.imerg_environment.requests.get', return_value=response) as get, self.assertRaises(ImergUnavailable):
            _read(URL, 9999999999, 'test-private-token')
        get.assert_called_once()


class ImergEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI(); self.app.include_router(router)
        self.app.dependency_overrides[require_auth] = lambda: {'role': 'Citizen'}
        self.client = TestClient(self.app)
        p = patch('backend.citizen_environment.imerg_service.fetch', return_value={'source': 'NASA GPM IMERG Early'})
        self.fetch = p.start(); self.addCleanup(p.stop)

    def test_authenticated_endpoint_and_no_store(self):
        r = self.client.get('/citizen/environment/precipitation?latitude=12&longitude=75')
        self.assertEqual(r.status_code, 200); self.assertEqual(r.headers['cache-control'], 'no-store')
        self.fetch.assert_called_once_with(12, 75)

    def test_invalid_latitude_longitude_and_missing_coordinates(self):
        for query in ['', '?latitude=12', '?latitude=91&longitude=75', '?latitude=12&longitude=181', '?latitude=nan&longitude=75', '?latitude=12&longitude=inf']:
            self.assertEqual(self.client.get('/citizen/environment/precipitation'+query).status_code, 422)
        self.fetch.assert_not_called()

    def test_clean_unavailable_response(self):
        self.fetch.side_effect = ImergUnavailable()
        r = self.client.get('/citizen/environment/precipitation?latitude=12&longitude=75')
        self.assertEqual(r.status_code, 503); self.assertEqual(r.json(), {'detail': 'Live data unavailable.'})

    def test_authentication_required(self):
        self.app.dependency_overrides.clear()
        with patch('backend.auth.dependencies.authenticate_profile', side_effect=HTTPException(401, 'Unauthorized')):
            self.assertEqual(self.client.get('/citizen/environment/precipitation?latitude=12&longitude=75').status_code, 401)
        self.fetch.assert_not_called()

    def test_endpoint_does_not_call_smap_ml_weather_or_coordinate_fallback(self):
        with patch('services.smap_environment.smap_service.fetch', side_effect=AssertionError('SMAP called')), \
             patch('rainfall_service.simulated_rainfall_mm', side_effect=AssertionError('synthetic called')), \
             patch('services.weather_extension.WeatherExtensionService.fetch_weather_context', side_effect=AssertionError('prediction weather called')), \
             patch('predict.predict', side_effect=AssertionError('ML called')):
            self.assertEqual(self.client.get('/citizen/environment/precipitation?latitude=12&longitude=75').status_code, 200)

    def test_predict_risk_keeps_prediction_rainfall_and_never_calls_imerg(self):
        import backend_api
        req = backend_api.PredictRequest(latitude=12, longitude=75, deformation_mm=5., velocity_mm_yr=12., coherence=0.8, slope_deg=24., soil_moisture_pct=45.)
        with patch.object(backend_api, 'predict', return_value={'risk_label': 'LOW'}) as predict, \
             patch('services.weather_extension.WeatherExtensionService.fetch_weather_context', return_value={}), \
             patch('services.weather_extension.WeatherExtensionService.fetch_rainfall_mm', return_value={'rainfall_mm': 3}), \
             patch.object(backend_api, 'load_zones', return_value={}), patch.object(backend_api, 'find_zone_matches', return_value=[]), \
             patch.object(backend_api, 'highest_zone_risk', return_value='LOW'), \
             patch('services.safe_route_service.SafeRouteService.build_guidance', return_value={}), \
             patch('services.imerg_environment.imerg_service.fetch', side_effect=AssertionError('IMERG entered ML')):
            backend_api.predict_risk(req, {})
            self.assertEqual(predict.call_args.kwargs['rainfall_mm'], 3)
            self.assertEqual(predict.call_args.kwargs['soil_moisture_pct'], 45.)
        self.assertIn('/citizen/environment/precipitation', backend_api.app.openapi()['paths'])
