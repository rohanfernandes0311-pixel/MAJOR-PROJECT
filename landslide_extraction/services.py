from __future__ import annotations

from pathlib import Path
import ipaddress
import os
import socket
from urllib.parse import urlsplit

import requests
from fastapi import HTTPException, UploadFile

from .background import run_extraction_job
from .extractor import inspect_pdf
from .storage import LocalExtractionStorage, job_registry, new_job_id

MAX_PDF_BYTES = 20 * 1024 * 1024

def _check_size(content: bytes) -> bytes:
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds the 20 MiB size limit")
    return content


def _read_upload_bytes(upload: UploadFile) -> bytes:
    content = upload.file.read(MAX_PDF_BYTES + 1)
    if not isinstance(content, (bytes, bytearray)):
        content = bytes(content)
    return _check_size(bytes(content))


def _load_source_from_url(url: str) -> tuple[bytes, str]:
    try:
        parsed = urlsplit(url)
        allowed = {host.strip().lower() for host in os.getenv("EXTRACTION_ALLOWED_HOSTS", "").split(',') if host.strip()}
        if parsed.scheme != 'https' or not parsed.hostname or parsed.hostname.lower() not in allowed or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("URL not permitted")
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("URL not permitted")
        # Only administrator-configured provider hosts are trusted. Redirects
        # cannot transfer that trust to another host or an internal service.
        with requests.get(url, timeout=30, allow_redirects=False, stream=True) as response:
            if not 200 <= response.status_code < 300:
                raise ValueError("Download failed")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                content.extend(chunk)
                _check_size(content)
        return bytes(content), Path(parsed.path).name or "landslide.pdf"
    except HTTPException:
        raise
    except (ValueError, OSError, requests.RequestException) as exc:
        raise HTTPException(status_code=400, detail="Unable to download PDF from an approved URL") from exc


def _load_source_from_path(path: str) -> tuple[bytes, str]:
    allowed_root = Path(os.getenv("EXTRACTION_SOURCE_DIR") or str(Path(__file__).resolve().parents[1] / 'data' / 'landslide_extraction')).resolve()
    source_path = Path(path).resolve()
    if not source_path.is_relative_to(allowed_root):
        raise HTTPException(status_code=400, detail="PDF path is outside the configured source directory")
    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=400, detail="PDF path does not exist")
    with source_path.open('rb') as handle:
        return _check_size(handle.read(MAX_PDF_BYTES + 1)), source_path.name


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


def submit_job(background_tasks, content: bytes, source_name: str, owner_id: str | None = None) -> str:
    storage = LocalExtractionStorage()
    job_id = new_job_id()
    try:
        source_path = storage.save_source_bytes(job_id, source_name, _check_size(content))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid PDF filename") from exc

    try:
        inspection = inspect_pdf(str(source_path))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid or corrupt PDF") from exc

    if inspection.get("page_count", 0) <= 0:
        raise HTTPException(status_code=400, detail="Invalid or corrupt PDF")

    job_registry.create(job_id=job_id, source_name=source_name, source_path=str(source_path), owner_id=owner_id)
    background_tasks.add_task(run_extraction_job, job_id, str(source_path), source_name)
    return job_id
