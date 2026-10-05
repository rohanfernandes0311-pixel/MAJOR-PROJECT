"""Demo Admin exports use existing accounts and isolated SQLite fixtures only."""
from io import BytesIO
from unittest import TestCase
from unittest.mock import patch

from openpyxl import load_workbook
from sqlalchemy import event, select

import backend_api as api
from backend.auth.middleware import get_current_user
from database.models import User, Location
from services.httpsms_export import HEADERS
from services.simulation_demonstration import RegisteredWorkbookRequest
from tests import test_simulation_recipient_selection as selection_fixtures


class DemoAdminRecipientTests(TestCase):
    def setUp(self):
        self.fixture = selection_fixtures.SimulationRecipientSelectionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db, self.app, self.client = self.fixture.db, self.fixture.app, self.fixture.client
        self.operator = {'role': 'Admin', 'sub': 'operator'}
        self.app.dependency_overrides[get_current_user] = lambda: self.operator
        for uid, name, phone in [('operator', 'Original Admin', '9000000000'),
                                 ('admin-two', 'Admin 2', '9000000001'),
                                 ('admin-three', 'Admin 3', '9000000002')]:
            self.db.add(User(uid=uid, name=name, phone_number=phone, phone_hash=uid,
                             created_at='2020-01-01', last_login='2020-01-01', role='Admin',
                             alert_enabled=0, last_device_hash='fixture'))
        # One Admin outside every demo zone and one with no location at all.
        self.db.add(Location(user_id='operator', latitude=12.4, longitude=75.8, last_updated='2020-01-01'))
        self.db.add(Location(user_id='admin-two', latitude=0, longitude=0, last_updated='2020-01-01'))
        self.db.commit()
        directory = self.directory()
        self.ids = {row['name']: row['recipientId'] for row in directory}

    def directory(self):
        response = self.client.get('/admin/simulation/visual/demo-admin-recipients')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        return response.json()['recipients']

    def selection(self, location='Madikeri', risk='HIGH', admins=(), users=()):
        selected = self.fixture.selection(location, risk, list(users))
        selected.demo_admin_recipient_ids = [self.ids[name] for name in admins]
        return selected

    def export(self, *selections):
        request = RegisteredWorkbookRequest(scenarios=list(selections))
        response = self.client.post('/admin/simulation/visual/registered-excel', json=request.model_dump())
        self.assertEqual(response.status_code, 200, response.text)
        book = load_workbook(BytesIO(response.content))
        self.addCleanup(book.close)
        return book

    def test_1_only_admin_two(self):
        book = self.export(self.selection(admins=['Admin 2']))
        self.assertEqual([row[1] for row in list(book.active.values)[1:]], ['+919000000001'])

    def test_2_only_admin_three(self):
        book = self.export(self.selection(admins=['Admin 3']))
        self.assertEqual([row[1] for row in list(book.active.values)[1:]], ['+919000000002'])

    def test_3_both_explicitly_selected_admins(self):
        book = self.export(self.selection('Chittalli', admins=['Admin 2', 'Admin 3']))
        self.assertEqual({row[1] for row in list(book.active.values)[1:]}, {'+919000000001', '+919000000002'})
        self.assertEqual(book.active['C2'].value, book.active['C3'].value)

    def test_4_no_admin_selected_exports_only_selected_registered_user(self):
        book = self.export(self.selection(users=['two']))
        self.assertEqual([row[1] for row in list(book.active.values)[1:]], [self.fixture.phones['two']])
        response = self.client.post('/admin/simulation/visual/registered-excel', json={
            'scenarios': [self.selection().model_dump()]})
        self.assertEqual(response.status_code, 422)

    def test_5_high_and_critical_messages_remain_distinct(self):
        book = self.export(self.selection(admins=['Admin 2']), self.selection(risk='CRITICAL', admins=['Admin 2']))
        self.assertEqual(book.sheetnames, ['Madikeri HIGH', 'Madikeri CRITICAL'])
        self.assertIn('Madikeri / HIGH', book.worksheets[0]['C2'].value)
        self.assertIn('stay alert', book.worksheets[0]['C2'].value)
        self.assertIn('Madikeri / CRITICAL', book.worksheets[1]['C2'].value)
        self.assertIn('Move away', book.worksheets[1]['C2'].value)

    def test_6_virajpet_message_does_not_contain_madikeri(self):
        book = self.export(self.selection('Virajpet', 'CRITICAL', ['Admin 3']))
        self.assertIn('Virajpet / CRITICAL', book.active['C2'].value)
        self.assertNotIn('Madikeri', book.active['C2'].value)

    def test_7_multi_location_groups_keep_correct_recipients_and_messages(self):
        book = self.export(self.selection(admins=['Admin 2']), self.selection('Virajpet', 'CRITICAL', ['Admin 3']))
        self.assertEqual(book.sheetnames, ['Madikeri HIGH', 'Virajpet CRITICAL'])
        for sheet, phone, group in zip(book, ['+919000000001', '+919000000002'], ['Madikeri / HIGH', 'Virajpet / CRITICAL']):
            self.assertEqual(sheet.max_row, 2)
            self.assertEqual(sheet['B2'].value, phone)
            self.assertIn(group, sheet['C2'].value)
            self.assertTrue(sheet['C2'].value.startswith('SIMULATION ONLY'))
            self.assertEqual(tuple(sheet.values)[0], HEADERS)
            self.assertEqual(sheet['A2'].value, '+919876543210')
            self.assertEqual(sheet['B2'].data_type, 's')
            self.assertIsNone(sheet['D2'].value)

    def test_8_admins_outside_or_without_locations_and_opt_in_can_be_selected(self):
        self.assertEqual(len(self.directory()), 2)
        book = self.export(self.selection(admins=['Admin 2', 'Admin 3']))
        self.assertEqual(book.active.max_row, 3)

    def test_9_directory_masks_phones_and_never_exposes_operator_or_uid(self):
        rows = self.directory()
        self.assertEqual(set(self.ids), {'Admin 2', 'Admin 3'})
        for row in rows:
            self.assertEqual(set(row), {'recipientId', 'name', 'phone', 'selectable'})
            self.assertTrue(row['selectable'])
            self.assertNotIn('admin-two', row['recipientId'])
            self.assertNotIn('admin-three', row['recipientId'])
            self.assertIn('*', row['phone'])
            self.assertNotIn('900000000', row['phone'])

    def test_10_11_12_export_is_read_only_and_never_calls_transports(self):
        before_users = self.db.execute(select(User.__table__)).all()
        before_locations = self.db.execute(select(Location.__table__)).all()
        selected = self.selection(admins=['Admin 2', 'Admin 3'])
        def read_only(conn, cursor, statement, parameters, context, executemany):
            self.assertTrue(statement.lstrip().upper().startswith('SELECT'), statement)
        event.listen(self.fixture.engine, 'before_cursor_execute', read_only)
        try:
            with patch.object(api, 'send_sms_alert') as sms, patch.object(api, 'create_alert') as alert, patch.object(self.db, 'commit') as commit, patch('requests.sessions.Session.request', side_effect=AssertionError('No provider calls')):
                self.directory()
                self.export(selected)
            sms.assert_not_called()
            alert.assert_not_called()
            commit.assert_not_called()
            self.assertEqual(before_users, self.db.execute(select(User.__table__)).all())
            self.assertEqual(before_locations, self.db.execute(select(Location.__table__)).all())
        finally:
            event.remove(self.fixture.engine, 'before_cursor_execute', read_only)

    def test_13_citizen_and_anonymous_access_denied(self):
        request = {'scenarios': [self.selection(admins=['Admin 2']).model_dump()]}
        self.operator = {'role': 'Citizen', 'sub': 'one'}
        self.assertEqual(self.client.get('/admin/simulation/visual/demo-admin-recipients').status_code, 403)
        self.assertEqual(self.client.post('/admin/simulation/visual/registered-excel', json=request).status_code, 403)
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get('/admin/simulation/visual/demo-admin-recipients').status_code, 401)
        self.assertEqual(self.client.post('/admin/simulation/visual/registered-excel', json=request).status_code, 401)

    def test_operator_citizen_unknown_and_changed_role_recipients_rejected(self):
        import hashlib
        for uid in ('operator', 'one', 'missing'):
            selected = self.selection()
            selected.demo_admin_recipient_ids = ['demo-admin-' + hashlib.sha256(uid.encode()).hexdigest()]
            response = self.client.post('/admin/simulation/visual/registered-excel', json={'scenarios': [selected.model_dump()]})
            self.assertEqual(response.status_code, 422)
        selected = self.selection(admins=['Admin 2'])
        self.db.get(User, 'admin-two').role = 'Citizen'
        self.db.commit()
        response = self.client.post('/admin/simulation/visual/registered-excel', json={'scenarios': [selected.model_dump()]})
        self.assertEqual(response.status_code, 422)

    def test_invalid_phone_is_disabled_and_rejected_and_duplicates_deduplicated(self):
        selected = self.selection(admins=['Admin 2'])
        self.db.get(User, 'admin-two').phone_number = 'invalid'
        self.db.commit()
        self.assertFalse(next(row for row in self.directory() if row['name'] == 'Admin 2')['selectable'])
        selected = self.selection(admins=['Admin 2'])
        response = self.client.post('/admin/simulation/visual/registered-excel', json={'scenarios': [selected.model_dump()]})
        self.assertEqual(response.status_code, 422)
        self.db.get(User, 'admin-two').phone_number = self.db.get(User, 'admin-three').phone_number
        self.db.commit()
        book = self.export(self.selection(admins=['Admin 2', 'Admin 3', 'Admin 2']))
        self.assertEqual(book.active.max_row, 2)

    def test_missing_operator_identity_cannot_list_or_export_admins(self):
        request = {'scenarios': [self.selection(admins=['Admin 2']).model_dump()]}
        self.operator = {'role': 'Admin'}
        self.assertEqual(self.client.get('/admin/simulation/visual/demo-admin-recipients').status_code, 403)
        self.assertEqual(self.client.post('/admin/simulation/visual/registered-excel', json=request).status_code, 403)

    def test_mixed_recipients_use_real_registered_phones_without_geofence_bypass(self):
        book = self.export(self.selection(admins=['Admin 2'], users=['two']))
        self.assertEqual({row[1] for row in list(book.active.values)[1:]}, {'+919000000001', self.fixture.phones['two']})
        selected = self.selection(admins=['Admin 2'], users=['one'])
        response = self.client.post('/admin/simulation/visual/registered-excel', json={'scenarios': [selected.model_dump()]})
        self.assertEqual(response.status_code, 422)
