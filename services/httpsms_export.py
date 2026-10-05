"""In-memory httpSMS upload preparation. This module has no SMS transport."""
from io import BytesIO
import re

from openpyxl import Workbook
from openpyxl.styles import Font

HEADERS = ("FromPhoneNumber", "ToPhoneNumber", "Content", "SendTime(optional)")
MISSING_SENDER = "httpSMS sender number is not configured. Please configure HTTPSMS_FROM_NUMBER."


def normalize_phone(value: str) -> str | None:
    """Accept Indian mobile numbers or explicitly international E.164 numbers."""
    phone = re.sub(r"\s+", "", str(value or ""))
    if re.fullmatch(r"[6-9][0-9]{9}", phone):
        return "+91" + phone
    if re.fullmatch(r"91[6-9][0-9]{9}", phone):
        return "+" + phone
    if phone.startswith("+91"):
        return phone if re.fullmatch(r"\+91[6-9][0-9]{9}", phone) else None
    return phone if re.fullmatch(r"\+[1-9][0-9]{7,14}", phone) else None


def generate_alert_message(risk_level: str, location: str) -> str:
    risk = risk_level.upper()
    if risk == "HIGH":
        guidance = "Please stay alert, avoid unstable slopes, and follow the recommended safer route."
    elif risk == "CRITICAL":
        guidance = "Move away from unstable slopes immediately and follow the recommended safer route."
    else:
        raise ValueError("httpSMS export requires a HIGH or CRITICAL danger zone.")
    return f"LANDsense ALERT: {risk.title()} landslide risk detected near {location}. {guidance}"


def select_sms_recipients(members: list[dict]) -> dict:
    affected = [member for member in members if member["inside"]]
    phones, invalid = set(), []
    duplicate_count = 0
    for member in affected:
        if not member["_alert_enabled"]:
            continue
        phone = normalize_phone(member["_phone_number"])
        if not phone:
            invalid.append(member["_user_id"])
        elif phone in phones:
            duplicate_count += 1
        else:
            phones.add(phone)
    return {"affected_count": len(affected), "sms_eligible_count": len(phones),
            "duplicate_count": duplicate_count, "_invalid_user_ids": invalid,
            "_phones": sorted(phones)}


def build_workbook(sender: str, phones: list[str], message: str) -> bytes:
    return build_location_workbook(sender, [("LANDsense", phones, message)])


def build_location_workbook(sender: str, selections: list[tuple[str, list[str], str]]) -> bytes:
    """Keep each explicitly selected location/risk group in its own worksheet."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, phones, message in selections:
        sheet = workbook.create_sheet(title[:31])
        sheet.append(HEADERS)
        for phone in phones:
            sheet.append((sender, phone, message, None))
            # Explicit text avoids formula interpretation and preserves phone digits/+.
            for cell in sheet[sheet.max_row][:3]:
                cell.data_type = "s"
                cell.number_format = "@"
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        for column, width in zip("ABCD", (24, 24, 100, 24)):
            sheet.column_dimensions[column].width = width
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def export_filename(risk: str, location: str) -> str:
    safe_location = re.sub(r"[^A-Za-z0-9_-]+", "_", location).strip("_")[:80] or "Zone"
    return f"LANDsense_{risk}_{safe_location}_httpSMS.xlsx"
