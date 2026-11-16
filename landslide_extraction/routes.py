from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from backend.auth.middleware import get_current_user
from fastapi.responses import FileResponse

from .background import run_extraction_job
from .schemas import ExtractionJobCreateResponse, ExtractionJobStatusResponse
from .services import prepare_source, submit_job
from .storage import job_registry


router = APIRouter(prefix="/landslide-extraction", tags=["landslide-extraction"])


@router.post("/jobs", response_model=ExtractionJobCreateResponse, status_code=202)
def create_extraction_job(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None),
    path: str | None = Form(default=None),
    url: str | None = Form(default=None),
    payload: dict = Depends(get_current_user),
) -> ExtractionJobCreateResponse:
    content, source_name = prepare_source(upload=file, path=path, url=url)
    job_id = submit_job(background_tasks, content, source_name, owner_id=str(payload.get("sub", "")))
    return ExtractionJobCreateResponse(job_id=job_id, status="queued")


@router.get("/jobs/{job_id}", response_model=ExtractionJobStatusResponse)
def get_extraction_job(job_id: str, payload: dict = Depends(get_current_user)) -> ExtractionJobStatusResponse:
    record = job_registry.get(job_id)
    if not record or not record.get("owner_id") or record["owner_id"] != payload.get("sub"):
        raise HTTPException(status_code=404, detail="Job not found")
    return ExtractionJobStatusResponse(**record)


@router.get("/jobs/{job_id}/download")
def download_extraction_job(job_id: str, payload: dict = Depends(get_current_user)) -> FileResponse:
    record = job_registry.get(job_id)
    if not record or not record.get("owner_id") or record["owner_id"] != payload.get("sub"):
        raise HTTPException(status_code=404, detail="Job not found")
    if record.get("status") != "complete" or not record.get("output_csv"):
        raise HTTPException(status_code=409, detail="Job is not complete yet")
    return FileResponse(record["output_csv"], media_type="text/csv", filename=f"{job_id}.csv")
