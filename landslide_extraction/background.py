from __future__ import annotations

from .extractor import extract_named_tables, extract_tabular_inventory, inspect_pdf, rows_to_csv
from .storage import LocalExtractionStorage, job_registry


DEFAULT_TABLE_HINTS = ["Table 1", "Table 2", "Table 3", "Table 4"]


def run_extraction_job(job_id: str, source_path: str, source_name: str, table_hints: list[str] | None = None) -> None:
    storage = LocalExtractionStorage()
    try:
        job_registry.update(job_id, status="running")
        inspection = inspect_pdf(source_path)

        document_type = inspection.get("document_type", "unknown")
        if document_type == "narrative_report":
            named_rows = extract_named_tables(source_path, table_hints or DEFAULT_TABLE_HINTS)
            rows = [row for bucket in named_rows.values() for row in bucket]
        else:
            rows = extract_tabular_inventory(source_path)

        output_path = storage.output_csv_path(job_id, source_name)
        rows_to_csv(rows, str(output_path))
        job_registry.update(
            job_id,
            status="complete",
            output_csv=str(output_path),
            row_count=len(rows),
            inspection=inspection,
        )
    except Exception:  # pragma: no cover - safety net for background execution
        job_registry.update(job_id, status="failed", error="PDF extraction failed")
