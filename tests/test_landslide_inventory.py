from __future__ import annotations

import csv
import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import backend_api
from services.landslide_inventory_service import (
    DATASET_NAME,
    REQUIRED_COLUMNS,
    import_inventory_csv,
    parse_inventory_csv,
)
import services.landslide_inventory_service as inventory_service


def _write_csv(rows: list[dict[str, str]], columns: list[str] | None = None) -> Path:
    handle = tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", suffix=".csv", delete=False)
    with handle:
        writer = csv.DictWriter(handle, fieldnames=columns or sorted(REQUIRED_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return Path(handle.name)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "S_No": "1",
        "Latitude": "18.55",
        "Longitude": "73.90",
        "Slide_Name": "Test slide",
        "State": "Maharashtra",
        "District": "Pune",
        "Subdivision_Or_Taluk": "Mulshi",
        "Material_Involved": "Debris",
        "Movement_Type": "Slide",
        "Initiation_Year": "2020",
        "History_Date_Remarks": "",
        "Source_Page": "1",
    }
    row.update(overrides)
    return row


class _Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return list(self.values)


class _ImportDb:
    def __init__(self):
        self.event_ids: set[str] = set()
        self.persisted: list[dict[str, object]] = []
        self.commits = 0
        self.rollbacks = 0

    def scalars(self, _statement):
        return _Rows(self.event_ids)

    def execute(self, _statement, parameters=None):
        if parameters:
            self.persisted.extend(parameters)
            self.event_ids.update(str(item["event_id"]) for item in parameters)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _ApiDb:
    def __init__(self, records):
        self.records = records

    def scalar(self, _statement):
        return len(self.records)

    def scalars(self, _statement):
        return _Rows(self.records)

    def execute(self, _statement):
        years = [item.initiation_year for item in self.records if item.initiation_year]
        return SimpleNamespace(one=lambda: (min(years), max(years)))


class LandslideInventoryTests(unittest.TestCase):
    def tearDown(self):
        for path in getattr(self, "paths", []):
            path.unlink(missing_ok=True)

    def remember(self, path: Path) -> Path:
        self.paths = getattr(self, "paths", []) + [path]
        return path

    def test_csv_parsing_preserves_supported_fields_and_dataset_label(self):
        path = self.remember(_write_csv([_row(History_Date_Remarks="16-08-2020")]))
        records, report = parse_inventory_csv(path)

        self.assertEqual(report.total_rows, 1)
        self.assertEqual(report.skipped, 0)
        self.assertEqual(records[0]["event_id"], "field-validated-inventory:1")
        self.assertEqual(records[0]["initiation_year"], 2020)
        self.assertEqual(records[0]["history_date_remarks"], "16-08-2020")
        self.assertEqual(records[0]["source_type"], "dataset")
        self.assertNotIn("severity", records[0])

    def test_invalid_coordinates_and_missing_required_values_are_skipped(self):
        path = self.remember(_write_csv([
            _row(S_No="1", Latitude="not-a-coordinate"),
            _row(S_No="2", Longitude="181"),
            _row(S_No="", Latitude="18.5", Longitude="73.9"),
        ]))
        records, report = parse_inventory_csv(path)

        self.assertEqual(records, [])
        self.assertEqual(report.skipped, 3)
        self.assertEqual(report.invalid_coordinates, 2)
        self.assertEqual(report.missing_required, 1)

    def test_missing_dates_are_allowed_and_malformed_years_become_null(self):
        path = self.remember(_write_csv([
            _row(S_No="1", Initiation_Year="0"),
            _row(S_No="2", Initiation_Year="corrupt"),
        ]))
        records, report = parse_inventory_csv(path)

        self.assertEqual([item["initiation_year"] for item in records], [None, None])
        self.assertEqual(report.invalid_years, 1)

    def test_missing_columns_fail_closed(self):
        path = self.remember(_write_csv([{"S_No": "1"}], columns=["S_No"]))
        with self.assertRaisesRegex(ValueError, "Missing required inventory columns"):
            parse_inventory_csv(path)

    def test_import_is_persistent_and_idempotent(self):
        path = self.remember(_write_csv([_row(S_No="1"), _row(S_No="2")]))
        db = _ImportDb()

        first = import_inventory_csv(path, db=db, imported_at="2026-08-15T00:00:00Z")
        second = import_inventory_csv(path, db=db, imported_at="2026-08-15T00:01:00Z")

        self.assertEqual(first["imported"], 2)
        self.assertEqual(first["duplicates"], 0)
        self.assertEqual(second["imported"], 0)
        self.assertEqual(second["duplicates"], 2)
        self.assertEqual(len(db.persisted), 2)
        self.assertEqual(db.commits, 2)

    def test_api_response_is_read_only_historical_dataset_data(self):
        record = SimpleNamespace(
            event_id="field-validated-inventory:1",
            latitude=18.55,
            longitude=73.9,
            initiation_year=2020,
            slide_name="Test slide",
            state="Maharashtra",
            district="Pune",
            subdivision_or_taluk="Mulshi",
            material_involved="Debris",
            movement_type="Slide",
            history_date_remarks=None,
            source_page="1",
            source_name=DATASET_NAME,
            source_type="dataset",
        )

        response = backend_api.landslide_inventory(_={"sub": "user-a"}, db=_ApiDb([record]))

        self.assertEqual(response["source_type"], "dataset")
        self.assertEqual(response["classification"], "historical landslide inventory")
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["date_range"], {"from": 2020, "to": 2020})
        self.assertEqual(response["landslides"][0]["source_type"], "dataset")

    def test_importer_has_no_alert_or_sms_delivery_dependency(self):
        source = inspect.getsource(inventory_service)
        self.assertNotIn("create_alert", source)
        self.assertNotIn("send_sms", source)


if __name__ == "__main__":
    unittest.main()
