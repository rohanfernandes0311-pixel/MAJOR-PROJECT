from __future__ import annotations

import argparse
import csv
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import LandslideInventory


DATASET_NAME = "Field-validated landslide inventory"
SOURCE_TYPE = "dataset"
EVENT_ID_PREFIX = "field-validated-inventory"
REQUIRED_COLUMNS = {
    "S_No",
    "Latitude",
    "Longitude",
    "State",
    "District",
    "Slide_Name",
    "Subdivision_Or_Taluk",
    "Material_Involved",
    "Movement_Type",
    "Initiation_Year",
    "History_Date_Remarks",
    "Source_Page",
}
MISSING_TEXT = {"", "-", "--", "#n/a", "n/a", "na", "nan", "null", "none"}


@dataclass
class ImportReport:
    dataset: str = DATASET_NAME
    source_type: str = SOURCE_TYPE
    total_rows: int = 0
    imported: int = 0
    duplicates: int = 0
    skipped: int = 0
    invalid_coordinates: int = 0
    missing_required: int = 0
    malformed_rows: int = 0
    invalid_years: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return None if normalized.casefold() in MISSING_TEXT else normalized


def _coordinate(value: object, minimum: float, maximum: float) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and minimum <= number <= maximum else None


def _year(value: object, report: ImportReport) -> int | None:
    normalized = _text(value)
    if normalized is None or normalized == "0":
        return None
    try:
        year = int(normalized)
    except ValueError:
        report.invalid_years += 1
        return None
    current_year = datetime.now(timezone.utc).year
    if year < 1800 or year > current_year:
        report.invalid_years += 1
        return None
    return year


def parse_inventory_csv(csv_path: str | Path) -> tuple[list[dict[str, object]], ImportReport]:
    """Parse the supplied point inventory without inventing missing attributes."""
    path = Path(csv_path)
    report = ImportReport()
    records: list[dict[str, object]] = []

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_COLUMNS - columns)
        if missing_columns:
            raise ValueError(f"Missing required inventory columns: {', '.join(missing_columns)}")

        for row in reader:
            report.total_rows += 1
            try:
                source_record_id = _text(row.get("S_No"))
                state = _text(row.get("State"))
                latitude = _coordinate(row.get("Latitude"), -90, 90)
                longitude = _coordinate(row.get("Longitude"), -180, 180)

                if latitude is None or longitude is None:
                    report.skipped += 1
                    report.invalid_coordinates += 1
                    continue
                if source_record_id is None or state is None:
                    report.skipped += 1
                    report.missing_required += 1
                    continue

                records.append({
                    "event_id": f"{EVENT_ID_PREFIX}:{source_record_id}",
                    "source_record_id": source_record_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "initiation_year": _year(row.get("Initiation_Year"), report),
                    "slide_name": _text(row.get("Slide_Name")),
                    "state": state,
                    "district": _text(row.get("District")),
                    "subdivision_or_taluk": _text(row.get("Subdivision_Or_Taluk")),
                    "material_involved": _text(row.get("Material_Involved")),
                    "movement_type": _text(row.get("Movement_Type")),
                    "history_date_remarks": _text(row.get("History_Date_Remarks")),
                    "source_name": DATASET_NAME,
                    "source_page": _text(row.get("Source_Page")),
                    "source_type": SOURCE_TYPE,
                })
            except (AttributeError, TypeError, ValueError):
                report.skipped += 1
                report.malformed_rows += 1

    return records, report


def _chunks(records: list[dict[str, object]], size: int = 1000) -> Iterator[list[dict[str, object]]]:
    for start in range(0, len(records), size):
        yield records[start:start + size]


INSERT_COLUMNS = (
    "event_id", "source_record_id", "latitude", "longitude", "initiation_year",
    "slide_name", "state", "district", "subdivision_or_taluk", "material_involved",
    "movement_type", "history_date_remarks", "source_name", "source_page",
    "source_type", "imported_at",
)


def _bulk_insert(session: Session, pending: list[dict[str, object]]) -> None:
    """Use PostgreSQL COPY for the real Neon import and a generic test fallback."""
    bind = session.get_bind() if hasattr(session, "get_bind") else None
    if bind is not None and bind.dialect.name == "postgresql" and pending:
        proxied_connection = session.connection().connection
        driver_connection = getattr(proxied_connection, "driver_connection", proxied_connection)
        column_sql = ", ".join(INSERT_COLUMNS)
        with driver_connection.cursor().copy(
            f"COPY {LandslideInventory.__tablename__} ({column_sql}) FROM STDIN"
        ) as copy:
            for record in pending:
                copy.write_row(tuple(record[column] for column in INSERT_COLUMNS))
        return

    for batch in _chunks(pending):
        session.execute(insert(LandslideInventory), batch)


def import_inventory_csv(
    csv_path: str | Path,
    db: Session | None = None,
    *,
    dry_run: bool = False,
    imported_at: str | None = None,
) -> dict[str, object]:
    records, report = parse_inventory_csv(csv_path)
    if dry_run:
        report.imported = len(records)
        return report.to_dict()

    owns_session = db is None
    session = db or SessionLocal()
    batch_time = imported_at or datetime.now(timezone.utc).isoformat()
    try:
        existing_ids = set(session.scalars(
            select(LandslideInventory.event_id).where(LandslideInventory.source_name == DATASET_NAME)
        ).all())
        pending: list[dict[str, object]] = []
        pending_ids: set[str] = set()
        for record in records:
            event_id = str(record["event_id"])
            if event_id in existing_ids or event_id in pending_ids:
                report.duplicates += 1
                continue
            pending_ids.add(event_id)
            pending.append({**record, "imported_at": batch_time})

        _bulk_insert(session, pending)
        session.commit()
        report.imported = len(pending)
        return report.to_dict()
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the field-validated landslide inventory into Neon PostgreSQL.")
    parser.add_argument("csv_path", help="Path to landslide_inventory_field_validated.csv")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate without writing to PostgreSQL")
    args = parser.parse_args()
    print(import_inventory_csv(args.csv_path, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
