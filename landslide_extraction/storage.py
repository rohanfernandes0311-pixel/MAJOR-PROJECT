from __future__ import annotations

import csv
import uuid
from pathlib import Path
from threading import Lock
from typing import Iterable


class LocalExtractionStorage:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(__file__).resolve().parents[1] / "data" / "landslide_extraction"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_job_dir(self, job_id: str) -> Path:
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def save_source_bytes(self, job_id: str, source_name: str, content: bytes) -> Path:
        job_dir = self.create_job_dir(job_id)
        source_path = job_dir / source_name
        source_path.write_bytes(content)
        return source_path

    def output_csv_path(self, job_id: str, source_name: str) -> Path:
        stem = Path(source_name).stem or "landslide_extraction"
        return self.create_job_dir(job_id) / f"{stem}.csv"


def rows_to_csv(rows: list[dict], out_path: str) -> str:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return str(path)


class JobRegistry:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = Lock()

    def create(self, job_id: str, source_name: str, source_path: str) -> dict:
        record = {
            "job_id": job_id,
            "status": "queued",
            "source_name": source_name,
            "source_path": source_path,
            "output_csv": None,
            "row_count": 0,
            "error": None,
            "inspection": None,
        }
        with self._lock:
            self._jobs[job_id] = record
        return record

    def update(self, job_id: str, **changes) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            self._jobs[job_id].update(changes)
            return dict(self._jobs[job_id])

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return dict(record) if record else None


def new_job_id() -> str:
    return uuid.uuid4().hex


job_registry = JobRegistry()
