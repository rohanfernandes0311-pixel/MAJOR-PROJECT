"""Selection integration tests: isolated SQLite and existing simulation fixtures only."""
from io import BytesIO
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend_api as api
from backend.auth.middleware import get_current_user
from database.connection import get_db
from database.models import User, Location
from services.httpsms_export import HEADERS
from services.simulation_demonstration import (
    CONFIG, RegisteredSelection, RegisteredWorkbookRequest, registered_excel, registered_scenario, router,
)


class SimulationRecipientSelectionTests(TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
        for model in (User, Location):
            model.__table__.create(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        # Reuse coordinates and numbers already present in project test fixtures.
        fixtures = [('one', 'Virajpet', 0, '9148682207'), ('two', 'Madikeri', 0, '7795530769'),
                    ('three', 'Chittalli', 0, '9876543210'), ('four', 'Virajpet', 1, '8888888888'),
                    ('five', 'Virajpet', 2, '9999999999')]
        self.phones = {}
        for uid, location, index, phone in fixtures:
            person = CONFIG['locations'][location]['users'][index]
            self.db.add(User(uid=uid, phone_number=phone, phone_hash=uid, name=uid,
                             created_at='2020-01-01', last_login='2020-01-01', role='Citizen',
                             alert_enabled=1, last_device_hash='fixture'))
            self.db.add(Location(user_id=uid, latitude=person['latitude'], longitude=person['longitude'], last_updated='2020-01-01'))
            self.phones[uid] = '+91' + phone
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {'role': 'Admin'}
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)
        sender = patch.dict('os.environ', {'HTTPSMS_FROM_NUMBER': '+919876543210'})
        sender.start()
        self.addCleanup(sender.stop)

    def selection(self, location, risk, uids):
        scenario, _ = registered_scenario(location, risk, self.db)
        return RegisteredSelection(location=location, risk=risk, revision=scenario['revision'],
                                   message=scenario['message'], recipient_ids=[api._safe_citizen_id(uid) for uid in uids])

    def export(self, *selections):
        response = registered_excel(RegisteredWorkbookRequest(scenarios=list(selections)), {}, self.db)
        workbook = load_workbook(BytesIO(response.body))
        self.addCleanup(workbook.close)
        return workbook

    def test_1_select_only_user_1_among_three_locations_and_multiple_eligible(self):
        scenario, _ = registered_scenario('Virajpet', 'HIGH', self.db)
        self.assertEqual(sum(p['recipientEligible'] for p in scenario['people']), 3)
        workbook = self.export(self.selection('Virajpet', 'HIGH', ['one']))
        self.assertEqual([row[1] for row in list(workbook.active.values)[1:]], [self.phones['one']])

    def test_2_select_only_user_2(self):
        workbook = self.export(self.selection('Madikeri', 'CRITICAL', ['two']))
        self.assertEqual([row[1] for row in list(workbook.active.values)[1:]], [self.phones['two']])

    def test_3_and_8_two_locations_keep_exact_recipients_risks_and_messages(self):
        workbook = self.export(self.selection('Virajpet', 'HIGH', ['one']), self.selection('Madikeri', 'CRITICAL', ['two']))
        self.assertEqual(workbook.sheetnames, ['Virajpet HIGH', 'Madikeri CRITICAL'])
        self.assertEqual(sum(sheet.max_row - 1 for sheet in workbook), 2)
        for sheet, uid, location, risk in [(workbook.worksheets[0], 'one', 'Virajpet', 'HIGH'),
                                          (workbook.worksheets[1], 'two', 'Madikeri', 'CRITICAL')]:
            self.assertEqual(sheet['B2'].value, self.phones[uid])
            self.assertIn(f'{location} / {risk}', sheet['C2'].value)
            self.assertNotIn('CRITICAL' if risk == 'HIGH' else 'HIGH', sheet['C2'].value)

    def test_4_eligible_unselected_and_omitted_selection_never_export(self):
        for selection in (self.selection('Virajpet', 'HIGH', []),
                          self.selection('Madikeri', 'HIGH', [])):
            with self.assertRaises(HTTPException) as error:
                self.export(selection)
            self.assertEqual(error.exception.status_code, 422)

    def test_5_outside_users_and_unknown_ids_rejected(self):
        for uid in ('two', 'outside'):
            with self.assertRaises(HTTPException) as error:
                self.export(self.selection('Virajpet', 'HIGH', [uid]))
            self.assertEqual(error.exception.status_code, 422)

    def test_6_and_7_risk_specific_messages(self):
        high = self.export(self.selection('Virajpet', 'HIGH', ['one'])).active['C2'].value
        critical = self.export(self.selection('Madikeri', 'CRITICAL', ['two'])).active['C2'].value
        self.assertIn('stay alert', high)
        self.assertIn('Move away', critical)

    def test_11_columns_and_phone_text_preserved(self):
        sheet = self.export(self.selection('Virajpet', 'HIGH', ['one'])).active
        self.assertEqual(tuple(sheet.values)[0], HEADERS)
        self.assertEqual(sheet['B2'].data_type, 's')
        self.assertIsNone(sheet['D2'].value)

    def test_12_no_transport_alert_write_or_user_mutation(self):
        before = self.db.execute(select(User.__table__)).all()
        with patch.object(api, 'send_sms_alert') as sms, patch.object(api, 'create_alert') as alert, patch.object(self.db, 'commit') as commit, patch('requests.sessions.Session.request', side_effect=AssertionError('No provider HTTP calls allowed')):
            self.export(self.selection('Virajpet', 'HIGH', ['one']))
        sms.assert_not_called()
        alert.assert_not_called()
        commit.assert_not_called()
        self.assertEqual(before, self.db.execute(select(User.__table__)).all())

    def test_location_change_and_gps_change_require_fresh_selection(self):
        selected = self.selection('Virajpet', 'HIGH', ['one'])
        selected.location = 'Madikeri'
        with self.assertRaises(HTTPException) as error:
            self.export(selected)
        self.assertEqual(error.exception.status_code, 409)
        selected = self.selection('Virajpet', 'HIGH', ['one'])
        other = self.db.get(Location, 'two')
        user = self.db.get(Location, 'one')
        user.latitude, user.longitude = other.latitude, other.longitude
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.export(selected)
        self.assertEqual(error.exception.status_code, 409)

    def test_admin_only_lists_and_exports(self):
        request = RegisteredWorkbookRequest(scenarios=[self.selection('Virajpet', 'HIGH', ['one'])]).model_dump()
        self.app.dependency_overrides[get_current_user] = lambda: {'role': 'Citizen'}
        self.assertEqual(self.client.get('/admin/simulation/visual/recipients?location=Virajpet&risk=HIGH').status_code, 403)
        self.assertEqual(self.client.post('/admin/simulation/visual/registered-excel', json=request).status_code, 403)
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get('/admin/simulation/visual/recipients?location=Virajpet&risk=HIGH').status_code, 401)

    def test_duplicate_request_and_disabled_user_rejected(self):
        selected = self.selection('Virajpet', 'HIGH', ['one'])
        with self.assertRaises(HTTPException):
            self.export(selected, selected)
        self.db.get(User, 'one').alert_enabled = 0
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.export(self.selection('Virajpet', 'HIGH', ['one']))
        self.assertEqual(error.exception.status_code, 422)

    def test_actor_uses_existing_centers_without_location_writes_or_recipient_changes(self):
        from sqlalchemy import event
        before_users = self.db.execute(select(User.__table__)).all()
        before_locations = self.db.execute(select(Location.__table__)).all()
        def read_only_sql(conn, cursor, statement, parameters, context, executemany):
            self.assertTrue(statement.lstrip().upper().startswith('SELECT'), 'Simulation actor must not persist location events or records')
        event.listen(self.engine, 'before_cursor_execute', read_only_sql)
        try:
            for location, profile in CONFIG['locations'].items():
                for risk in CONFIG['risk_levels']:
                    scenario, members = registered_scenario(location, risk, self.db)
                    actor = scenario['adminActor']
                    self.assertEqual(actor['status'], 'available')
                    self.assertEqual([actor['latitude'], actor['longitude']], profile['center'])
                    self.assertFalse(actor['recipientEligible'])
                    self.assertEqual(len(scenario['people']), len(members))
                    self.assertTrue(all(p['displayId'] != actor['label'] for p in scenario['people']))
                    self.assertEqual([p['inside'] for p in scenario['people']], [m['inside'] for m in members])
            self.assertEqual(before_users, self.db.execute(select(User.__table__)).all())
            self.assertEqual(before_locations, self.db.execute(select(Location.__table__)).all())
        finally:
            event.remove(self.engine, 'before_cursor_execute', read_only_sql)

    def test_actor_without_existing_valid_position_reports_unavailable(self):
        from services.simulation_mode_service import SimulationModeService
        from geofencing import point_in_polygon
        for location in CONFIG['locations']:
            for risk in CONFIG['risk_levels']:
                scenario, _ = registered_scenario(location, risk, self.db)
                actor = scenario['adminActor']
                ring = scenario['dangerZone']['geometry']['coordinates'][0]
                self.assertTrue(point_in_polygon(actor['latitude'], actor['longitude'], ring))
                for position in (None, [], [float('nan'), actor['longitude']], CONFIG['locations']['Virajpet' if location != 'Virajpet' else 'Madikeri']['center']):
                    unavailable = SimulationModeService.admin_actor(location, risk, position, scenario['dangerZone'])
                    self.assertEqual(unavailable['status'], 'unavailable')
                    self.assertNotIn('latitude', unavailable)
