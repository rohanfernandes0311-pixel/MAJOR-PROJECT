from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from unittest import TestCase, mock

from landslide_extraction.extractor import extract_named_tables, extract_tabular_inventory, inspect_pdf, rows_to_csv, verify_color_coded_cells


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FakePage:
    def __init__(self, text: str, tables: list[list[list[str]]]):
        self._text = text
        self._tables = tables

    def extract_text(self):
        return self._text

    def extract_tables(self):
        return self._tables

    def flush_cache(self):
        return None

    def to_image(self, resolution=175):
        class _Image:
            original = object()

        return _Image()


class FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class ExtractorTests(TestCase):
    def test_inspect_pdf_reports_page_count_and_text_layer(self):
        result = inspect_pdf(str(FIXTURES / "blank_two_page.pdf"))
        self.assertEqual(result["page_count"], 2)
        self.assertFalse(result["has_text_layer"])

    def test_extract_tabular_inventory_preserves_row_count(self):
        pages = [
            FakePage(
                "Inventory Table",
                [[
                    ["State_UT", "Target_Area_sqkm", "Source"],
                    ["Himachal Pradesh", "42093", "Table 1, p.2"],
                    ["Uttarakhand", "39009", "Table 1, p.2"],
                ]],
            ),
            FakePage(
                "Inventory Table Continued",
                [[
                    ["State_UT", "Target_Area_sqkm", "Source"],
                    ["Sikkim", "4979", "Table 1, p.2"],
                ]],
            ),
        ]
        with mock.patch("landslide_extraction.extractor.pdfplumber.open", return_value=FakePdf(pages)):
            rows = extract_tabular_inventory(str(FIXTURES / "blank_two_page.pdf"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["source_pdf"], "blank_two_page.pdf")
        self.assertEqual(rows[0]["source_page"], "1")

    def test_extract_named_tables_returns_hinted_rows(self):
        pages = [
            FakePage(
                "Table 1 State status",
                [[
                    ["State_UT", "Year_of_Initiation", "Status_ColorCoded_Columns"],
                    ["Sikkim (06)", "2021", "R&D Phase; Experimental Bulletin & Ground Testing"],
                ]],
            )
        ]
        with mock.patch("landslide_extraction.extractor.pdfplumber.open", return_value=FakePdf(pages)):
            rows = extract_named_tables(str(FIXTURES / "blank_one_page.pdf"), ["Table 1"])
        self.assertIn("Table 1", rows)
        self.assertEqual(len(rows["Table 1"]), 1)
        self.assertEqual(rows["Table 1"][0]["State_UT"], "Sikkim (06)")

    def test_rows_to_csv_writes_utf8_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "rows.csv"
            result = rows_to_csv([
                {"source_pdf": "a.pdf", "source_page": "1", "section_reference": "page 1", "State_UT": "Kerala"}
            ], str(out_path))
            self.assertEqual(result, str(out_path))
            with out_path.open(encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("Kerala", content)

    def test_verify_color_coded_cells(self):
        pages = [FakePage("Table 1", [])]
        with mock.patch("landslide_extraction.extractor.pdfplumber.open", return_value=FakePdf(pages)):
            verify_color_coded_cells(str(FIXTURES / "blank_one_page.pdf"), 1)
