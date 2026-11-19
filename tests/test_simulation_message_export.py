from io import BytesIO
import unittest

from openpyxl import load_workbook

from services.httpsms_export import HEADERS, build_workbook


class SimulationMessageExportTests(unittest.TestCase):
    def test_kannada_content_round_trips_in_existing_xlsx_columns(self):
        message = (
            "SIMULATION ONLY — Madikeri / HIGH: "
            "ಸಿಮ್ಯುಲೇಶನ್ ಮಾತ್ರ — LANDsense ಸಿಮ್ಯುಲೇಶನ್ ಎಚ್ಚರಿಕೆ: "
            "ಮಡಿಕೇರಿಯಲ್ಲಿ ಹೆಚ್ಚಿನ ಭೂಕುಸಿತ ಅಪಾಯವನ್ನು ಅನುಕರಿಸಲಾಗಿದೆ."
        )
        payload = build_workbook("18005550199", ["+919148682207"], message)
        workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
        try:
            sheet = workbook.active
            self.assertEqual(tuple(cell.value for cell in sheet[1]), HEADERS)
            self.assertEqual(sheet[2][2].value, message)
            self.assertEqual(sheet[2][3].value, None)
            self.assertEqual(sheet[2][2].data_type, "s")
        finally:
            workbook.close()


if __name__ == "__main__":
    unittest.main()
