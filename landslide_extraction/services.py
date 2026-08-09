from __future__ import annotations

from pathlib import Path

import requests
from fastapi import HTTPException, UploadFile

from .background import run_extraction_job
from .extractor import inspect_pdf
from .storage import LocalExtractionStorage, job_registry, new_job_id


def _read_upload_bytes(upload: UploadFile) -> bytes:
    content = upload.file.read()
    if not isinstance(content, (bytes, bytearray)):
        content = bytes(content)
    return bytes(content)


def _load_source_from_url(url: str) -> tuple[bytes, str]:
    response = requests.get(url, timeout=30)
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="Unable to download PDF from URL")
    source_name = Path(url.split("?")[0]).name or "landslide.pdf"
    return response.content, source_name


def _load_source_from_path(path: str) -> tuple[bytes, str]:
    source_path = Path(path)
    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=400, detail="PDF path does not exist")
    return source_path.read_bytes(), source_path.name


def prepare_source(upload: UploadFile | None = None, path: str | None = None, url: str | None = None) -> tuple[bytes, str]:
    provided = [value for value in (upload, path, url) if value]
    if len(provided) != 1:
        raise HTTPException(status_code=400, detail="Provide exactly one PDF source: file, path, or url")

    if upload is not None:
        content = _read_upload_bytes(upload)
        source_name = upload.filename or "landslide.pdf"
    elif path is not None:
        content, source_name = _load_source_from_path(path)
    else:
        assert url is not None
        content, source_name = _load_source_from_url(url)

    return content, source_name


def submit_job(background_tasks, content: bytes, source_name: str) -> str:
    storage = LocalExtractionStorage()
    job_id = new_job_id()
    source_path = storage.save_source_bytes(job_id, source_name, content)

    try:
        inspection = inspect_pdf(str(source_path))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid or corrupt PDF") from exc

    if inspection.get("page_count", 0) <= 0:
        raise HTTPException(status_code=400, detail="Invalid or corrupt PDF")

    job_registry.create(job_id=job_id, source_name=source_name, source_path=str(source_path))
    background_tasks.add_task(run_extraction_job, job_id, str(source_path), source_name)
    return job_id
