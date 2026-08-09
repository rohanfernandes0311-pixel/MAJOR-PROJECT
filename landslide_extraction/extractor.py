from __future__ import annotations

import gc
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = " | ".join(part.strip() for part in text.split("\n") if part.strip())
    return text.strip()


def _normalize_row(row: list[Any], width: int) -> list[str]:
    normalized = [_clean_cell(cell) for cell in row[:width]]
    if len(normalized) < width:
        normalized.extend([""] * (width - len(normalized)))
    return normalized


def _row_is_blank(row: Iterable[str]) -> bool:
    return not any(cell.strip() for cell in row)


def _looks_like_header(row: list[str]) -> bool:
    joined = " ".join(row).lower()
    return any(token in joined for token in ("state", "district", "rank", "source", "sl_no")) and not any(
        char.isdigit() for char in joined
    )


def _row_to_record(headers: list[str], values: list[str], path: str, page_number: int, table_reference: str) -> dict[str, str]:
    record: dict[str, str] = {
        "source_pdf": Path(path).name,
        "source_page": str(page_number),
        "section_reference": table_reference,
    }
    for index, header in enumerate(headers):
        key = header or f"column_{index + 1}"
        record[key] = values[index] if index < len(values) else ""
    return record


def _dedupe_exact(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in rows:
        marker = tuple(sorted(row.items()))
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped


def inspect_pdf(path: str) -> dict:
    reader = PdfReader(path)
    page_count = len(reader.pages)
    has_text_layer = False
    table_pages = 0
    sample_text = ""

    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                has_text_layer = True
                sample_text = sample_text or text
            tables = page.extract_tables() or []
            if tables:
                table_pages += 1
            page.flush_cache()
            del page
            gc.collect()
            if page_number >= 3:
                break

    lowered = sample_text.lower()
    if table_pages:
        document_type = "tabular_inventory"
    elif any(token in lowered for token in ("table 1", "table 2", "table 3", "district", "inventory")):
        document_type = "narrative_report"
    elif page_count > 1 and not has_text_layer:
        document_type = "map_atlas"
    else:
        document_type = "unknown"

    return {
        "page_count": page_count,
        "has_text_layer": has_text_layer,
        "document_type": document_type,
    }


def extract_tabular_inventory(path: str) -> list[dict]:
    rows: list[dict[str, str]] = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            for table_index, table in enumerate(tables, start=1):
                normalized = [_normalize_row(row, max(len(row) for row in table)) for row in table if row]
                if not normalized:
                    continue
                headers = normalized[0]
                previous_record: dict[str, str] | None = None
                for values in normalized[1:]:
                    if _row_is_blank(values):
                        continue
                    if _looks_like_header(values):
                        continue
                    record = _row_to_record(headers, values, path, page_number, f"page {page_number} table {table_index}")
                    if previous_record and _is_continuation(previous_record, record):
                        previous_record = _merge_continuation(previous_record, record)
                        rows[-1] = previous_record
                    else:
                        rows.append(record)
                        previous_record = record
            page.flush_cache()
            del page
            gc.collect()
    return _dedupe_exact(rows)


def _is_continuation(previous_record: dict[str, str], record: dict[str, str]) -> bool:
    payload_keys = [key for key in record.keys() if key not in {"source_pdf", "source_page", "section_reference"}]
    previous_nonempty = sum(1 for key in payload_keys if previous_record.get(key, "").strip())
    current_nonempty = sum(1 for key in payload_keys if record.get(key, "").strip())
    return current_nonempty and current_nonempty <= 2 and previous_nonempty >= current_nonempty


def _merge_continuation(previous_record: dict[str, str], record: dict[str, str]) -> dict[str, str]:
    merged = dict(previous_record)
    for key, value in record.items():
        if key in {"source_pdf", "source_page", "section_reference"}:
            continue
        if value and merged.get(key):
            if value not in merged[key]:
                merged[key] = f"{merged[key]} | {value}"
        elif value:
            merged[key] = value
    return merged


def extract_named_tables(path: str, table_hints: list[str]) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {hint: [] for hint in table_hints}
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").lower()
            tables = page.extract_tables() or []
            for hint in table_hints:
                if hint.lower() not in text:
                    continue
                hint_rows: list[dict] = []
                for table_index, table in enumerate(tables, start=1):
                    normalized = [_normalize_row(row, max(len(row) for row in table)) for row in table if row]
                    if len(normalized) < 2:
                        continue
                    headers = normalized[0]
                    for values in normalized[1:]:
                        if _row_is_blank(values) or _looks_like_header(values):
                            continue
                        hint_rows.append(_row_to_record(headers, values, path, page_number, f"{hint} page {page_number} table {table_index}"))
                results[hint].extend(_dedupe_exact(hint_rows))
            page.flush_cache()
            del page
            gc.collect()
    return results


def verify_color_coded_cells(path: str, page_number: int) -> None:
    with pdfplumber.open(path) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise IndexError("page_number out of range")
        page = pdf.pages[page_number - 1]
        try:
            image = page.to_image(resolution=175)
            _ = image.original
        finally:
            page.flush_cache()
            del page
            gc.collect()


def rows_to_csv(rows: list[dict], out_path: str) -> str:
    from .storage import rows_to_csv as _rows_to_csv

    return _rows_to_csv(rows, out_path)
